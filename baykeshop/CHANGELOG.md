# BaykeShop 变更日志

## 2026-04-24 三层架构全面重构

### 概述
对项目的 API 层、Service 层、Model 层进行了全面审查和修复，覆盖 59 个文件，35 个测试全部通过，新增 3 个数据库迁移。

---

### P0 严重 BUG 修复（7 项）

| # | 问题 | 文件 | 修复 |
|---|------|------|------|
| 1 | BaseModel.save() 每次保存覆盖 site | `db/base.py:37` | 加 `if self._state.adding:` 仅创建时赋值 |
| 2 | 上传接口 CSRF 安全漏洞 | `api/upload/views.py:23` | 删 CsrfExemptSessionAuthentication，改用 TokenAuthentication |
| 3 | total_quantity 统计行数而非数量 | `models/orders.py:31-33` | 改为 Sum('quantity') 聚合 |
| 4 | remove() 返回值永远成功 | `services/base.py:86` | 改为 `deleted_count = ...` 适配软删除返回整数 |
| 5 | create_order() 无事务 | `services/order_service.py:85` | 用 transaction.atomic() 包裹 |
| 6 | handle_payment_success() 无事务 | `services/pay_service.py:62` | 用 transaction.atomic() 包裹 |
| 7 | 短信频率限制非原子 | `db/security.py:195` | 改为 cache.incr() 原子递增 |

### 层职责清理

**Model → Service 迁移：**
- 删 `BaykeShopOrders.is_virtual` / `virtual_content`（已由 `OrderService` 提供）
- 删 `BaykeArticleContent.description`（改为模板 filter `striptags`）
- 删 `BaykeArticleContent.next_article` / `prev_article`（已由 `ArticleService` 提供）
- `BaykeDictModel.get_key_value()` 大幅简化（去掉裸 except）

**Service 层清理：**
- 定义 `OrderServiceError`、`InsufficientStockError`、`InvalidQuantityError` 业务异常
- 删 `PayService.is_virtual_order()`（调用者直接调 `OrderService`）
- 删 `FollowService._build_filter()` 死代码
- 合并 `_uv_ration()` / `_pv_ration()` 为参数化方法
- 修复收藏列表 key 中英文不匹配（`favorite_service.py`、`follow_service.py`）

**API 层清理：**
- 删 `Meta.fields` 死代码（普通 Serializer 上的无效配置，3 处）
- 删 `WriteOperationThrottle` 死别名
- 新增 `ServiceResultMixin` 消除 member view 响应代码重复

### 数据库迁移

```python
member: 0008  # BaykeShopUser.mobile 字段调整
shop:   0009  # stock/sales → PositiveIntegerField, quantity → MinValueValidator
               # 新增 status_created_time_idx 索引
               # 新增 unique_user_order_comment 约束
system: 0003  # url → URLField, permission → ForeignKey
               # 新增 unique_visit_record 约束
```

### 性能优化
- `analysis_service.py` 改为 GROUP BY 单 SQL（原每天一条，7-30 次）
- `get_index_floors()` 使用 prefetch 缓存（去掉了额外 `values_list` 查询）
- `ship_orders()` 改为单 `update()`（原 N 次独立 save）
- `cached_list()` 修复 query_fn 重复调用

### 测试
- 35 个测试全部通过
- 新增 `tests/conftest.py` 覆盖缓存后端为 LocMemCache（解除 Redis 依赖）
