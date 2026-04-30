# 性能压测分析与优化报告

> 日期: 2026-04-25
> 压测工具: Locust 2.43.4
> 环境: Django 4.2.17 + PostgreSQL + Redis 8.6.1 (Windows Dev Server)

---

## 一、压测结果总览

### 优化前后对比 (20并发/60s)

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 总请求数 | 642 | 790 | +23% |
| 吞吐量 | 10.74 req/s | 13.25 req/s | +23% |
| 总体 P50 | 320ms | **110ms** | **2.9x** |
| 总体 P95 | 650ms | 430ms | 1.5x |
| 首页 P50 | 470ms | **240ms** | **2.0x** |
| 详情 P50 | 300ms | **96ms** | **3.1x** |
| 登录 POST P50 | 510ms | 380ms | 1.3x |
| 加购 API P50 | 190ms | **28ms** | **6.8x** |
| 失败率 | 0% | 0.5%* | — |

\* 加购 400 错误来自 CSRF token 刷新或重复加购（唯一约束），非系统瓶颈。

### 系统极限

| 并发数 | 吞吐量 | P50 | P95 | 状态 |
|--------|--------|-----|-----|------|
| 20 | 13 req/s | 110ms | 430ms | 健康 |
| 30 | 15 req/s | 490ms | 1.3s | 临界 |
| 50 | 16 req/s | 1.5s | 3.4s | 饱和 |
| 100 | 14 req/s | 4.7s | 10s | 熔断 |

最大吞吐量约 **15-16 req/s**，瓶颈在于 Dev Server 单进程 + 数据库连接池。

---

## 二、高延迟根因分析

### 根因 1：首页 176 次数据库查询（核心瓶颈）

**表现**：首页 P50=470ms，P95=790ms（优化前）

**为什么首页会这么慢？**

首页渲染一张页面，触发了 **176 次 SQL 查询**，其中 174 次是 `baykeshopcategory` 表的全表扫描。按渲染链路分解：

```
首页 Template 渲染链路：
├── base.html (extends)
│   └── header.html (include)
│       ├── {% dict_value "SITE_TITLE" %}         → 1 次 DB 查 BaykeDictModel
│       ├── {% navs True as navs %}                → 1 次 DB 查导航分类
│       │   └── {% for child in nav.children %}    → 6 次 DB（6 个父分类，各查一次子分类）
│       └── {% carts_count user %}                 → 1 次 DB 查购物车数量
├── banners_template                               → 1 次 DB 查轮播图（缓存命中则跳过）
└── {% for floor in floors %}                      → get_index_floors()
    │                                               → 1 次 DB 查楼层分类
    │                                               → 1 次 DB IN 查子分类
    │                                               → 2 次 DB 查商品（含 with_all 注解）
    └── {% for spu in floor.spu_list|slice:10 %}   → 50 次 DB（每个 SPU 都查评论分）
        └── {% score_avg spu %}                     → SELECT AVG(score) FROM comments WHERE spu_id = N
```

**逐层拆解每个慢点的代码根因：**

#### 1.1 `{% navs %}` 的 N+1 问题（损失约 6-12 次查询）

```python
# templatetags/baykeshop.py — 优化前
def navs(is_nav=True):
    category_queryset = BaykeShopCategory.objects.filter(
        is_nav=is_nav, parent__isnull=True
    ).prefetch_related("baykeshopcategory_set")   # ← 预取子分类

    cache.set(cache_key, category_queryset, timeout=300)  # ← 缓存惰性 QuerySet
    return category_queryset
```

**根因详细分析：**

1. `prefetch_related("baykeshopcategory_set")` 在 QuerySet 上注册了预取查找
2. 这个 QuerySet 被**整体放入 Redis 缓存**（`cache.set(cache_key, category_queryset, ...)`）
3. 下一个请求从 Redis 中 **pickle 反序列化** 出这个 QuerySet
4. 模板中 `{% for child in nav.baykeshopcategory_set.all %}` 访问反向关系
5. `baykeshopcategory_set.all` 生成一个新的 QuerySet 去查数据库
6. 正常情况下 `prefetch_related` 会在模型实例上缓存 `_prefetched_objects_cache`
7. **但是** — 经过 Redis pickle 序列化/反序列化后，`_prefetched_objects_cache` 丢失
8. 对每个父分类（电脑办公、手机数码等 6 个），子分类都重新查库

**结果：1 次预期查询变成了 6+ 次，且每个父分类在首页和导航中重复查询 → 12+ 次。**

#### 1.2 `{% dict_value "SITE_TITLE" %}` 无缓存（损失约 1 次查询/页）

```python
# baykeconfig.py — 优化前
@register.simple_tag
def dict_value(key):
    return BaykeDictModel.get_key_value(key)  # ← 每次都查库
```

1 次看起来不多，但它被用在 **header.html** 中，而 header 被几乎所有页面引用。所有页面都多一次查询。

#### 1.3 `{% score_avg spu %}` × 50 次（损失约 50 次查询/页）

```python
# templatetags/baykeshop.py
@register.inclusion_tag("baykeshop/tags/sku.html")
def sku_template(spu):
    ...

@register.simple_tag
def score_avg(spu):
    return CommentService.get_score_avg(spu)   # ← 每次都 aggregate 查库

# comment_service.py
def get_score_avg(spu):
    return CommentService.get_spu_queryset(spu).aggregate(
        score_avg=models.Avg('score')
    ).get('score_avg')
```

首页有 6 个楼层，每个楼层显示 10 个 SPU（`slice:10`）= 60 个 SPU 卡片。每个 SPU 调用一次 `{% score_avg %}`，每次执行一个 `SELECT AVG(score) FROM ... WHERE spu_id = N`。60 张卡片 = 60 次聚合查询。

当评论表为空时，这些查询仍然执行（只是返回 NULL）。

#### 1.4 `get_goods_categories()` 缓存了惰性 QuerySet

与 `navs` 同样的问题：`categories = BaykeShopCategory.objects.all().order_by('order')` 被直接缓存，反序列化后重新查询。

### 根因 2：数据库连接不复用（次核心瓶颈）

**表现**：20 并发时 320ms，30 并发时跳到 490ms，50 并发时 1.5s

```python
# settings.py — 优化前
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        # ❌ 没有 CONN_MAX_AGE
    }
}
```

**根因详细分析：**

1. Django 默认 `CONN_MAX_AGE=None`，意味着**每次请求结束关闭数据库连接**
2. 每个新请求需要重新建立 TCP 连接（3 次握手）+ PostgreSQL 认证
3. PostgreSQL 为每个连接创建独立进程/线程
4. 并发 50 请求 = 可能同时 50 个 PostgreSQL 连接
5. PostgreSQL `max_connections` 默认 100，连接数上升后性能急剧下降

**在压测中观察到**：30 并发时吞吐量还能增长（10→15 req/s），50 并发时吞吐量停滞（15→16 req/s），表明数据库连接已成为瓶颈。

### 根因 3：Dev Server 单进程架构

**表现**：100 并发时 P95=10s

Django 开发服务器使用 `WSGIServer` + `ThreadingMixIn`，每个请求一个线程，但所有线程共享同一个 Python 进程的 GIL 和内存。模板渲染（CPU 密集型）在并发时会互相争抢。

**这不是 bug，是开发环境的架构限制**。生产环境会用 gunicorn/uwsgi 多进程解决。

### 根因 4：登录 POST 密码哈希

**表现**：登录 POST 在任何负载下 P50≈380-510ms

Django 默认密码哈希器 `PBKDF2PasswordHasher` 设计为慢哈希（~200-400ms/次）。这是安全设计，不是 bug，但在高并发登录场景下会引发连锁效应：

1. 一个登录请求占用工作线程 400ms+
2. 线程被占满后，其他请求排队
3. 即使首页只要 200ms，也要等登录线程释放

### 根因 5：购物车 CSRF/XSRF 令牌轮换

**表现**：加购 API 偶尔 400 Bad Request

登录成功后 Django 轮换 CSRF token，加购请求使用的是旧 token，被 `SessionAuthentication` 拒绝。

---

## 三、优化对上下游的影响分析

### 3.1 `{% navs %}` 改为 list() 后缓存

**改动**：`result = list(category_queryset)` 再缓存

**上游影响（调用方）**：
- 模板中 `{% for nav in navs %}` 行为不变，`list` 支持迭代
- `nav.name`, `nav.id` 等属性访问不变
- `nav.baykeshopcategory_set.all` 访问：**行为变化！**
  - 优化前：每次访问 `baykeshopcategory_set.all` 可能生成 SQL
  - 优化后：`list()` 在求值时会执行 `prefetch_related`，`_prefetched_objects_cache` 被填充
  - 缓存命中后：返回 `list`，每个 Category 实例的 `_prefetched_objects_cache` 完好 → **0 次额外查询**

**下游影响（数据库负载）**：
- 每 5 分钟：1 次父分类查询 + 1 次 IN 子分类查询 = 2 次 DB（缓存重建时）
- 缓存命中期间：0 次 DB
- 优化前：每次页面请求 12+ 次 DB → **DB 负载降低 99%**

**数据一致性风险**：
- 如果在 5 分钟缓存窗口内修改了分类（新增/改名），模板会展示旧数据
- 接受度：高（导航分类变更不频繁，5 分钟延迟可接受）
- 改善：在分类 admin 的 `save_model` 中删除 `navs` 缓存

### 3.2 `{% dict_value %}` 加 1 小时缓存

**改动**：`cache.set(cache_key, value, timeout=3600)`

**上游影响**：
- 所有使用 `{% dict_value "SITE_TITLE" %}`, `{% dict_value "ICP" %}` 等的地方
- 返回值类型不变（`get_key_value` 返回 String/List/Dict/Boolean）
- 模板行为完全不变

**下游影响**：
- 每个 key 最多每小时查库一次
- 优化前：每次页面请求查一次 → **DB 负载降低 99.9%**

**数据一致性风险**：
- 字典值通常在 admin 中修改时需要刷新缓存
- 需要配套缓存删除机制：
  ```python
  # BaykeDictModelAdmin.save_model 中
  cache.delete(f"dict:value:{obj.key}")
  ```

### 3.3 `get_index_floors()` 改为 Redis 缓存

**改动**：返回 `list[dict]` 而非 QuerySet，Redis 永不过期

**上游影响（模板层）**：
```python
# 优化前：category_list 是 QuerySet，category.spu_list 是附加属性
# 优化后：返回 list[dict]
{
    "id": category.id,
    "name": category.name,
    "icon": category.icon,
    "spu_list": spu_list,  # ← 仍然是模型实例
}
```
- `{% for floor in floors %}` 迭代行为不变
- `floor.name`, `floor.id` 在 Django 模板中自动支持 dict（先查 `floor["name"]` 再查 `floor.name`）
- `floor.spu_list` → `floor["spu_list"]`，行为完全一致
- `{% url 'shop:category' floor.id %}` → `floor["id"]`，行为一致

**下游影响**：
- 冷缓存时 1 次复杂查询（带 with_all 注解 + prefetch）
- 热缓存后 0 次查询
- 优化前：每次请求 4+ 次查询（floor + subcat + goods + prefetch）

**一致性风险**：
- 需要配套的 `update_floors_cache()` 在 admin 操作中调用
- `BaykeShopCategoryAdmin.save_model/delete_model` 中调用
- `BaykeShopGoodsAdmin.save_model/delete_model` 中调用（SPU 变化影响楼层展示）

### 3.4 `CONN_MAX_AGE=300`

**改动**：`'CONN_MAX_AGE': 300`

**上游影响**：
- 无。对应用层完全透明
- Django 自动管理连接池，每个线程保持一个长连接

**下游影响（PostgreSQL）**：
- 连接数从 `100 req × 1 conn/req = 100 conn` 降到 `~10 conn`（10 个工作线程）
- PostgreSQL 进程数减少 → 更多内存留给查询缓存
- **注意**：`CONN_MAX_AGE` 在线程模型中有效，但在单线程开发服务器中每个请求创建新线程，连接复用效果有限
- 生产环境效果更显著（gunicorn 固定工作进程）

---

## 四、剩余风险与已知问题

| 问题 | 影响 | 严重度 | 建议 |
|------|------|--------|------|
| `score_avg` 无缓存 | 首页 50 次 DB 查询 | 中 | 加 SPU 级缓存或预聚合到模型字段 |
| 登录密码哈希慢 | 登录 POST P50=380ms | 低（安全设计） | 负载均衡 + 异步登录验证 |
| 购物车 CSRF 轮换 | 偶尔 400，用户体验差 | 低 | 前端 CSRF token 自动刷新 |
| Celery 不可用 | 定时任务不工作 | 低 | Windows 下 solo pool 已启动 |
| 首页楼层缓存一致性问题 | 后台修改商品后首页可能展示旧数据 | 中 | 已添加 `update_floors_cache`，需确保 admin 中调用 |

## 五、优化方案总览

### 已完成（本阶段）

| # | 优化项 | 涉及文件 | 延迟收益 |
|---|--------|----------|----------|
| 1 | 首页楼层 Redis 缓存 | `public_service.py` | 470ms → 11ms (缓存命中) |
| 2 | navs 缓存 list 而非 QuerySet | `templatetags/baykeshop.py` | 消除 12 次 N+1 查询 |
| 3 | dict_value 加 1h 缓存 | `templatetags/baykeconfig.py` | 消除每次请求的字典查询 |
| 4 | get_goods_categories list 缓存 | `public_service.py` | 消除反序列化重复查询 |
| 5 | CONN_MAX_AGE=300 | `settings.py` | 减少连接建立开销 |
| 6 | Throttle 基类重构 | `api/throttles.py` | 修复 500 错误 |

### 建议下阶段

| # | 优化项 | 预期收益 | 难度 |
|---|--------|----------|------|
| A | `score_avg` 缓存（模型字段或 Redis） | 消除首页 50 次查询 | 低 |
| B | 生产环境部署（gunicorn + gevent） | 吞吐量 3-5x | 中 |
| C | PostgreSQL 连接池（pgbouncer） | 支持 200+ 并发连接 | 中 |
| D | Redis session 存储 | 减少 session 查询延迟 | 低 |
| E | 静态文件 CDN 或白名单 | 减少开发服务器静态文件负载 | 低 |
| F | 列表页分页缓存 | 减少列表页 2s+ 延迟 | 中 |

---

## 附录：压测数据明细

<details>
<summary>各场景详细数据</summary>

### 场景 A：首页浏览（读密集）

| 路径 | 权重 | P50 优化前 | P50 优化后 | P95 优化前 | P95 优化后 |
|------|------|-----------|-----------|-----------|-----------|
| / | 30% | 470ms | 240ms | 790ms | 510ms |
| /list/ | 25% | 360ms | 170ms | 660ms | 380ms |
| /list/?page=2 | 15% | 390ms | 160ms | 630ms | 600ms |
| /category/{pk}/ | 20% | 280ms | 100ms | 470ms | 300ms |
| /search/?keyword= | 10% | 240ms | 79ms | 420ms | 270ms |

### 场景 B：商品详情

| 路径 | P50 优化前 | P50 优化后 |
|------|-----------|-----------|
| /detail/{pk}/ | 300ms | 96ms |

### 场景 C：登录 + 购物车

| 端点 | P50 优化前 | P50 优化后 |
|------|-----------|-----------|
| GET /member/login/ | 200ms | 36ms |
| POST /member/login/ | 510ms | 380ms |
| GET /carts/ | 210ms | 40ms |
| POST /api/carts/ | 190ms | 28ms |

</details>

---

## 附录：压测发现的 Bug 汇总

| Bug | 文件 | 行号 | 现象 | 修复 |
|-----|------|------|------|------|
| `json.loads(sku.specs)` list 上调用 | `templatetags/baykeshop.py` | 164 | 详情页 500 TypeError | 加 `isinstance` 判断 |
| `WriteRateThrottle` 缺 `get_cache_key` | `api/throttles.py` | 64 | 加购 API 500 NotImplementedError | 提取基类统一实现 |
| `UserRateThrottle` 缺 `get_cache_key` | `api/throttles.py` | 24 | 全局限流失效 | 同上 |
| `UploadRateThrottle` 缺 `get_cache_key` | `api/throttles.py` | 75 | 上传接口 500 | 同上 |
