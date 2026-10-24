# RewrZ 数据模型说明

本文档记录核心表结构、关系与业务约束，便于后续开发和迁移。

## 1. 核心实体

| 表名 | 说明 | 关键字段 |
|---|---|---|
| `users` | 后台用户 | `id`, `username`, `email`, `hashed_password`, `role`, `token_version` |
| `posts` | 内容主表 | `id`, `title`, `slug`, `post_type`, `status`, `visibility`, `author_id` |
| `comments` | 评论 | `id`, `post_id`, `parent_id`, `status`, `author_name` |
| `categories` | 分类 | `id`, `name`, `slug`, `parent_id` |
| `tags` | 标签 | `id`, `name`, `slug` |
| `formats` | 内容意图 | `id`, `name`, `slug` |
| `media` | 媒体元数据 | `id`, `filepath`, `file_type`, `mime_type`, `file_hash`, `file_size` |
| `settings` | 系统配置 | `id`, `key`, `value(JSON)`, `category`, `type` |
| `content_reactions` | 点赞/表态 | `id`, `target_type`, `target_id`, `visitor_token` |
| `login_attempts` | 登录审计 | `id`, `username`, `ip_address`, `success`, `reason` |
| `api_keys` | 外部 API 密钥 | `id`, `name`, `key_prefix`, `key_level`, `is_active`, `expires_at` |
| `traffic_minute_stats` | 分钟访问聚合（保留 48 小时） | `bucket_start`, `requests`, `page_views`, `beacon_page_views`, `peak_concurrency` |
| `traffic_hour_stats` | 小时访问聚合（保留 3 年） | `bucket_start`, `requests`, `page_views`, `beacon_page_views` |
| `traffic_dimensions_daily` | 每日 Top N 维度 | `day_start_utc`, `kind`, `value`, `hits` |
| `traffic_visitors_daily` | 每日访客哈希（UV 去重） | `day_start_utc`, `visitor_hash`, `hits` |
| `traffic_anomaly_sources` | 异常来源 IP（保留 7 天） | `ip`, `hits`, `reason`, `sample_path`, `last_seen` |

## 2. 关系结构

### 2.0 ER 图（核心关系）

```mermaid
erDiagram
    USERS ||--o{ POSTS : author_id
    POSTS ||--o{ COMMENTS : post_id
    COMMENTS ||--o{ COMMENTS : parent_id

    POSTS }o--o{ CATEGORIES : post_categories
    POSTS }o--o{ TAGS : post_tags
    POSTS }o--o{ FORMATS : post_formats

    USERS ||--o{ MEDIA : uploaded_by_id
```

### 2.1 多对多关系
- `posts` <-> `categories` 通过 `post_categories`
- `posts` <-> `tags` 通过 `post_tags`
- `posts` <-> `formats` 通过 `post_formats`

### 2.2 一对多关系
- `users` -> `posts`
- `posts` -> `comments`
- `comments` -> `comments`（父子评论）

## 3. 业务硬约束

### 3.1 内容类型约束
- `post_type` 只允许：`post`、`page`
- `article/micro/poem` 属于 `formats`，不是 `post_type`

### 3.2 路由语义约束
- 聚合页路径统一为 `/formats/{format_slug}`，避免与 `/{page_slug}` 冲突
- 媒体归档使用 `/archives/media/{media_slug}`，避免和 `/media` 静态目录冲突

### 3.3 配置存储约束
- `settings.value` 为 JSON 结构，读取时统一走 `crud_setting` 或中间件聚合能力
- 不建议在业务代码中散落硬编码 key 读取逻辑

### 3.4 用户认证约束
- `users.token_version` 用于用户级登录态失效控制
- 忘记密码使用一次性重置令牌：
  - `password_reset_token_hash`
  - `password_reset_sent_at`
  - `password_reset_expires_at`
- 密码重置成功后必须递增 `token_version`

### 3.5 访问统计约束
- `traffic_*` 只保存聚合结果，不保存逐条请求日志；正常访客仅存 HMAC 访客哈希，
  只有判定为可疑/异常的来源才保留原始 IP（最多 7 天）
- 每日维度与 UV 的 `day_start_utc` 存“站点自然日 00:00 对应的 UTC 时间”，
  查询时再按 `SITE_TIMEZONE` 还原，不能直接用 UTC 日期截断
- 回源维度（`path`/`referer`/`source_type`/`utm_source`）与前端上报维度（`beacon_*`）
  分开存放，查询时按主导来源二选一，不能相加
- 统计表由应用启动时的 `create_all` 自动创建，不需要单独执行 Alembic 迁移

## 4. 数据演进建议

- 历史数据冲突优先“迁移修复”，不建议在运行时增加兼容分支。
- 变更模型前先确认是否影响：
  - `crud/post.py` 的主类型归一化逻辑
  - 导入导出与备份恢复逻辑
  - 现有测试覆盖（`tests/test_crud_post.py`、`tests/test_data_manager_importers.py`）

## 5. 高风险改动点

- `posts.post_type`、`post_formats`：会影响前台路径、筛选、导入映射
- `settings` key 语义：会影响后台设置页和模板上下文
- `media.filepath`：会影响 URL 生成、清理、去重和变体缓存

## 6. 发布数据流（文章）

```mermaid
flowchart TD
    A[提交文章表单] --> B[API 校验 post_type 与字段]
    B --> C[CRUD 归一化格式 formats]
    C --> D[构建 Post 实体]
    D --> E[关联分类/标签/格式]
    E --> F[写入数据库]
    F --> G[返回文章详情/列表更新]
```
