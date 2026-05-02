# 深度性能分析：真实查询链追踪与隐藏瓶颈

> 基于 Django `connection.queries` 全链路追踪 + PostgreSQL 索引检查 + 模板渲染链路分析
> 日期: 2026-04-25

---

## 一、关键发现总览

本次深入分析发现了**之前报告中遗漏的 3 个关键瓶颈**，以及**2 个架构级问题**。

### 实际查询数（非预估，通过全链路追踪实测）

| 端点 | 总查询数 | Category N+1 | Comment N+1 | 主查询 | 用时 |
|------|----------|--------------|-------------|--------|------|
| HOMEPAGE (冷缓存) | **242** | ~185 | ~50 | ~7 | 488ms |
| LIST (冷缓存) | **287** | ~201 | ~70 | ~16 | 94ms |
| CATEGORY (冷缓存) | **307** | ~216 | ~70 | ~21 | 40ms |
| DETAIL | — | — | — | — | 查询异常 |

**之前报告的"176 次查询"是低估**——那只是 View 层的查询，不包括模板渲染阶段。加上模板后真实查询数是 242-307。

---

## 二、新发现的隐藏瓶颈

### 瓶颈 #1：`prefetch_related('category')` 对 M2M 字段完全失效 ⚠️

**严重程度: 严重 | 影响范围: 所有含 SPU 列表的页面**

这是最重要的发现。`BaykeShopGoods.category` 是 `ManyToManyField`，代码中多处用 `prefetch_related('category')` 预取，但实际不起作用。

**实测验证 (`_prefetched_objects_cache` 检查):**
```
Cache: {'category': <BaseQuerySet [BaykeShopCategory 对象]>}  ← 缓存确实存在
g.category.all() → 仍然生成新 SQL 查询                              ← 但不使用缓存!
```

**现象：**
- `_prefetched_objects_cache['category']` 中有数据（由 `prefetch_related` 填充）
- 但 `g.category.all()` **不检查这个缓存**，每次都生成新的 SQL
- 每个 SPU 生成 1 次 `SELECT ... FROM shop_baykeshopcategory INNER JOIN shop_baykeshopgoods_category WHERE baykeshopgoods_id = N`

**根因：**
- Django 4.2 的 `ManyRelatedManager` 在 `get_queryset()` 中检查缓存的代码路径与 `BaseQuerySet` 自定义类之间存在兼容性问题
- `BaseManager.get_queryset()` 返回 `BaseQuerySet`（非标准 `QuerySet`）
- Django 的 M2M 描述符在 `ForwardManyRelatedDescriptor.__get__()` 中创建 `RelatedManager`，其 `get_queryset()` 走的是标准 `Manager.get_queryset()`，没有触发自定义的缓存检查逻辑

**影响量化：**
- 首页 `get_index_floors()`: 160 个 SPU × 1 查询 = **160 次额外查询**（0.293s 构建时间中的大部分）
- 列表页: 20 个 SPU × 1 查询 = **20 次额外查询**
- 分类页: 20 个 SPU × 1 查询 = **20 次额外查询**
- 详情页推荐: 5 个推荐 SPU × 1 查询 = **5 次额外查询**

### 瓶颈 #2：CommentService 完全无缓存 × 模板 `score_avg` 高频调用

**严重程度: 严重 | 影响范围: 首页/列表/分类/详情所有页面**

`spu.html` 模板中存在 `{% score_avg spu %}`，对每个 SPU 执行一次评论聚合查询：

```sql
SELECT AVG(score) FROM shop_baykeshoporderscomment 
WHERE order_id IN (
    SELECT DISTINCT orders_id FROM shop_baykeshopordersgoods 
    WHERE sku__goods_id = ?  -- 每个 SPU 各自的 ID
) AND status = True
```

**量化影响：**

| 页面 | SPU 数量 | 额外查询 | 占比 |
|------|---------|---------|------|
| 首页 | 50 (5 层 × 10 SPU) | **50 queries** | 20% |
| 列表页 | 20 | **20 queries** | 7% |
| 分类页 | 20 | **20 queries** | 7% |
| 详情页 | 1 + 5 推荐 | **6 queries** | — |

**即使评论表为空（测试数据 0 条评论），查询仍然执行。** 只是返回 NULL。

此外，详情页中 `get_goods_like_score()` 和 `get_goods_comments_count()` 有**重复查询**：
```python
# goods_service.py:81-88
def get_goods_like_score(goods):
    gte_3 = CommentService.get_spu_queryset(spu).filter(score__gte=3).count()  # ← 1 次
    total = CommentService.get_comment_count(spu)                                # ← 1 次

def get_goods_comments_count(goods):
    return CommentService.get_comment_count(spu)                                 # ← 重复!
```

### 瓶颈 #3：`get_index_floors()` 构建楼层时的 N+1 双重问题

**严重程度: 中高 | 影响范围: 首页冷缓存时**

```
楼层构建 293ms 时间线分解:
├── 1 次: 查询 floor 父分类 (0.001s)
├── 1 次: prefetch 子分类 (0.000s)  ← 虽为 IN 查询，但后续还是走了个体查询
├── 6 次: 个体 parent_id = N 查询 (0.000s each)  ← 同上，prefetch 失效
├── 1 次: goods with_all() 查询 (0.008s)
├── 1 次: goods category prefetch 查询 (0.001s)
├── 160 次: goods_id = N 的类别查询 (individual)   ← M2M prefetch 失效!
│   └── 每个 SPU 分别查中间表 baykeshopgoods_category
└── Python 分组: ~120ms
```

这 293ms 只在冷缓存时发生。缓存热后为 0ms。但问题在于：**即使没有 Redis 缓存，prefetch 也应该消除这 160 次查询。** 现在是 prefetch 和缓存双重失效。

---

## 三、之前报告中正确但被低估的瓶颈

### 瓶颈 #4：模板渲染链的开销

**实际渲染链路深度：**
```
base.html
└── base_site.html (extends base.html)
    └── index.html / list.html / detail.html (extends base_site.html)
        ├── header.html (include)
        │   ├── carts_count → 1 次 SQL / Redis
        │   └── navs → 6 次 category 查询 (prefetch 失效)
        ├── banners / floors / page_obj (view context)
        │   └── spu.html (include × 50 / 20)
        │       ├── score_avg → 1 次 SQL per SPU
        │       └── spu.image_url → 注解字段，OK
        ├── footer.html (include)
        │   └── dict_value × 3 → 3 次已缓存
        └── sku.html / filters.html / pagination.html 等 inclusion_tag
```

5 层继承 + 4+ 个 include × 50+ 次 = **50+ 模板文件渲染**。每个 `{% include %}` 需要模板节点查找 + 解析 + 渲染。

### 瓶颈 #5：Session + Auth 中间件每请求开销

Django `SessionMiddleware` + `AuthenticationMiddleware` + `MessageMiddleware` 在每个请求上：

| 步骤 | 操作 | 耗时 |
|------|------|------|
| SessionMiddleware | 从 Redis 加载 session | 0.5-2ms |
| AuthenticationMiddleware | `User.objects.get(pk=user_id)` | 1-2ms |
| CSRFMiddleware | Token 验证 + 可选轮换 | 0.5-1ms |
| MessageMiddleware | 加载 messages | 0.2-0.5ms |
| **合计** | | **3-6ms/请求** |

20 并发时 3-6ms 不重要，但 100 并发时每个请求的 3-6ms 在 GIL 争用下放大。

### 瓶颈 #6：过滤器边栏查询无缓存

`filters.html` 中的标签每次页面加载时执行：
```python
parent_category_queryset → 1 次 SQL (无缓存)
brand_queryset → 1 次 SQL (无缓存)
child_category_queryset → 1-3 次 SQL (无缓存)
sort_template → 无 SQL（纯逻辑）
```

每个列表/分类页 **3-5 次额外查询**。品牌只有 6 条记录，但每次都查。

---

## 四、高并发系统瓶颈分析

### 4.1 Dev Server 架构限制

Django `runserver` = `WSGIServer` + `ThreadingMixIn`

| 并发数 | 线程数 | P50 | P95 | 吞吐量 | 瓶颈 |
|--------|--------|-----|-----|--------|------|
| 20 | 20 | 110ms | 430ms | 13 req/s | GIL + N+1 查询 |
| 50 | 50 | 490ms | 1.3s | 15.7 req/s | GIL 争用加剧 |
| 100 | 100 | 1.5s | 3.4s → **10s** | 14.1 req/s | **GIL 饱和 + 连接池耗尽** |

**吞吐量在 50→100 并发时不增反降**（15.7→14.1 req/s），这是典型的系统过载信号。

### 4.2 GIL 争用是隐藏杀手

模板渲染是 Python 字节码操作 → GIL 绑定。100 个线程同时渲染模板：
- 线程 A 渲染首页（242 次查询，大量 Python 对象创建）
- 线程 B 渲染列表页（287 次查询）
- 只有 1 个线程能运行 Python 代码

测试中单纯 SQL 时间仅 62-90ms，但总耗时达 488ms。**N+1 查询不仅增加 DB 负载，更通过大量 ORM 对象创建加剧 GIL 争用。**

### 4.3 数据库连接

`CONN_MAX_AGE=300` 后，每个线程持有 1 个连接。100 个并发线程 → PostgreSQL 上 100 个连接。虽然 PostgreSQL 默认 `max_connections=100` 能承受，但 `Sum()`、`Min()` 等聚合查询加上 160 次 N+1 查询在高并发下竞争加剧。

---

## 五、修复优先级排序

### P0：必须立即修复（性能提升 60%+）

| # | 问题 | 修复方案 | 预期效果 |
|---|------|---------|---------|
| 1 | Category N+1（首页 160 次） | 在 `get_index_floors()` 中用 `Prefetch` 对象+`to_attr` 或 `default_manager.all()` 替代 | 首页 242→82 查询 (-66%) |
| 2 | `score_avg` 无缓存 | 添加 SPU 级 Redis 缓存（1 小时 TTL），key=`comment:avg:{spu_id}` | 首页 82→32 查询 (-61%) |
| 3 | 列表/分类页 category N+1 | 在 `get_queryset()` 中将 `prefetch_related('category')` 改为 `Prefetch('category', queryset=BaykeShopCategory.objects.all())` | 列表 287→107 查询 (-63%) |

### P1：重要优化（性能提升 20%+）

| # | 问题 | 修复方案 | 预期效果 |
|---|------|---------|---------|
| 4 | 过滤器边栏无缓存 | 添加 5 分钟 Redis 缓存 | 列表减少 3-5 查询 |
| 5 | 详情页评论重复查询 | `get_goods_like_score` 返回 total count 复用 | 详情减少 1 查询 |
| 6 | Session 写开销 | Django 默认 `SESSION_SAVE_EVERY_REQUEST=False`（已默认），确认无额外写 | — |

### P2：架构优化

| # | 问题 | 修复方案 |
|---|------|---------|
| 7 | GIL 争用 | 生产环境用 gunicorn + gevent 或 uWSGI 多进程 |
| 8 | 连接池 | 部署 pgbouncer 或增加 `CONN_MAX_AGE` |
| 9 | 模板渲染链 | 首页楼层改用 `{% cache %}` 模板片段缓存 |
| 10 | 静态文件 | dev 环境用 whitenoise 或 CDN，减少 dev server 负载 |

---

## 六、验证过的假设 vs 被证伪的假设

| 假设 | 验证结果 | 证据 |
|------|---------|------|
| 首页 176 查询是最多的 | ❌ 列表页 287 查询更多 | 全链路追踪实测 |
| `prefetch_related('category')` 有效 | ❌ **完全失效** | `_prefetched_objects_cache` 存在但 `g.category.all()` 不走缓存 |
| `with_all()` 注解导致 prefetch 失效 | ❌ 简单 queryset 也失效 | 测试 A vs B 结果相同 |
| PostgreSQL 缺少关键索引 | ❌ 所有 FK 已自动索引 | `pg_indexes` 查询 |
| Comment 查询在空表时不执行 | ❌ **仍然执行** | 50 条 comment 查询在 0 评论时仍触发 |
| 模板渲染是纯 CPU 工作 | ⚠️ 部分正确 | 但 SQL 只占 62/488ms，大部分是 ORM 对象创建 + 模板渲染 |
| 470ms 延迟主要来自 SQL | ❌ SQL 仅 62-98ms | `connection.queries['time']` 统计 |
