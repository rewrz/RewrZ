# RewrZ 架构说明

本文档描述当前代码结构、关键设计决策与扩展边界，供后续维护与二次开发参考。

## 1. 总体架构

RewrZ 采用典型分层：

1. 表现层：Jinja2 模板 + HTMX（`rewrz/templates`）
2. 接口层：FastAPI 路由（`rewrz/api` + `rewrz/main.py` 动态路由）
3. 业务/数据访问层：CRUD（`rewrz/crud`）
4. 持久层：SQLAlchemy ORM + 数据库（`rewrz/models`、`rewrz/core/database.py`）
5. 横切能力：配置、安全、模板上下文、媒体处理、导入导出（`rewrz/core`）

### 1.1 架构图（逻辑视图）

```mermaid
flowchart LR
    U[浏览器 / 客户端] --> N[Nginx/反向代理]
    N --> A[FastAPI 应用 rewrz.main]
    A --> R[API 路由层 rewrz/api]
    A --> T[模板渲染层 rewrz/templates]
    R --> C[核心能力层 rewrz/core]
    R --> D[CRUD 层 rewrz/crud]
    D --> M[ORM 模型 rewrz/models]
    M --> DB[(SQLite/PostgreSQL)]
    C --> FS[(媒体与静态文件系统)]
```

## 2. 启动与生命周期

入口文件：`rewrz/main.py`

关键流程：
- `lifespan` 启动阶段执行建表与历史数据归一化（`normalize_legacy_article_post_type`）。
- 全局关闭自动 API 文档端点（`docs_url/redoc_url/openapi_url = None`）。
- 安装状态由 `settings.installation_complete` 判定，未安装走 `/installer`。
- 安装完成后，`/installer` 对外重定向，避免后台入口暴露。

### 2.1 启动流程图

```mermaid
flowchart TD
    S[应用启动] --> E{.env 是否存在}
    E -- 否 --> I[进入安装向导流程]
    E -- 是 --> L[加载配置 DynamicSettings]
    L --> T[create_all_tables]
    T --> N[归一化历史 post_type 数据]
    N --> R[按请求动态注册后台路由]
```

## 3. 路由组织策略

### 3.1 双路由版本策略
- 大量接口同时存在：
  - 新路径：`/api/v1/...`
  - 兼容路径：`/api/...`
- 目标是在迁移期间保留调用稳定性，最终按版本策略收敛。

### 3.2 动态后台路径
- 后台入口不写死 `/admin`，由 `ADMIN_PATH` 控制。
- 关键后台路由在运行时注册（`register_admin_routes()`），减少固定入口暴露。

### 3.3 静态与媒体路由
- `/static`：前端静态资源
- `/media`：媒体文件目录
- `/media/variant/...` 动态缩略图路由在静态挂载前定义，确保优先命中。

## 4. 数据与模型设计原则

### 4.1 内容模型硬约束
- `post_type` 仅允许：`post`、`page`
- `article/micro/poem` 作为 `formats`（内容意图）存在
- 图片/视频/音频/外链是媒体附件能力，不是主内容类型

### 4.2 关系概览
- `posts` 与 `categories/tags/formats` 为多对多关系
- `comments` 通过 `post_id` 关联文章
- `settings` 以 `key + JSON value` 存储可扩展配置
- `media` 独立存储元信息（路径、类型、大小、哈希、上传者）

详见：[`DATA_MODEL.md`](DATA_MODEL.md)

## 5. 安全架构

### 5.1 身份认证
- 管理登录成功后写入 `access_token` Cookie（JWT）。
- 受保护接口依赖 `get_current_user`。

### 5.2 CSRF
- 会话中维护 `csrf_token`。
- 后台写操作（POST/PUT/DELETE）要求 CSRF 令牌并调用 `verify_csrf_token`。

### 5.3 Cookie/Session 安全
- `should_use_secure_cookie` 根据配置与请求协议决定 `Secure`。
- `SessionMiddleware` 支持 `https_only`（由 `SESSION_HTTPS_ONLY` 控制）。

### 5.4 上传与导入防护
- 上传采用流式写入，限制大小，避免整文件读入内存。
- 备份 ZIP 导入执行路径越界、压缩比、条目数、总大小校验。

### 5.5 后台写请求安全流程

```mermaid
sequenceDiagram
    participant Client as 管理端前端
    participant API as FastAPI 接口
    participant Sec as security.py
    participant DB as 数据库

    Client->>API: POST/PUT/DELETE + Cookie + X-CSRF-Token
    API->>Sec: get_current_user()
    Sec-->>API: 用户对象 / 401
    API->>Sec: verify_csrf_token()
    Sec-->>API: 通过 / 403
    API->>DB: 执行业务写入
    DB-->>API: 提交结果
    API-->>Client: 200/201/204
```

### 5.6 导入备份数据流

```mermaid
flowchart TD
    A[上传备份 ZIP] --> B[流式写入临时文件]
    B --> C[校验文件体积上限]
    C --> D[安全解包校验]
    D --> E{路径/压缩比/数量是否安全}
    E -- 否 --> X[拒绝导入并清理临时文件]
    E -- 是 --> F[读取数据文件并执行导入]
    F --> G[恢复媒体文件]
    G --> H[返回导入统计结果]
```

### 5.7 评论审核与反垃圾流程

```mermaid
flowchart TD
    A[访客提交评论] --> B[CSRF 校验]
    B --> C[基础字段校验]
    C --> D[速率限制检查]
    D --> E[反垃圾引擎检查]
    E --> F{判定结果}
    F -- spam --> X[拒绝并返回错误]
    F -- pending --> P[写入待审核评论]
    F -- approve --> G[写入已通过评论]
    P --> H[后台审核通过/拒绝]
    G --> I[前台展示]
    H --> I
```

## 6. 性能与可维护性策略

- 尽量将复杂逻辑收敛到 `core/` 或 `crud/`，避免路由层膨胀。
- 大量列表查询在 CRUD 层统一管理，减少模板层散乱查询。
- 通过测试覆盖关键行为（路由版本、模型约束、导入/上传安全、事务回归）。

### 6.1 媒体上传到变体生成时序图

```mermaid
sequenceDiagram
    participant Admin as 管理端
    participant API as media.py 上传接口
    participant Proc as media_processor
    participant DB as 数据库
    participant Thumb as thumbnail_service
    participant FS as 文件系统

    Admin->>API: 上传文件 + X-CSRF-Token
    API->>API: 鉴权 + CSRF 校验
    API->>API: 流式写入临时文件并计算哈希
    API->>Proc: 校验类型/大小
    Proc-->>API: 校验结果
    API->>DB: 重复文件检查（hash + size）
    alt 非重复
        API->>FS: 原子替换到目标路径
        API->>Proc: 提取元数据/可选优化
        API->>DB: 写入 media 记录
        API->>Thumb: 预热媒体库预览变体
        Thumb-->>FS: 生成 variant 缓存文件
        API-->>Admin: 返回上传成功与资源 URL
    else 重复文件
        API-->>Admin: 返回已存在资源（is_duplicate=true）
    end
```

## 7. 扩展建议

新增功能建议顺序：
1. 明确模型约束（是否符合 `post_type/formats` 规则）
2. 新增/调整 ORM 与 Schema
3. 在 CRUD 实现事务与行为
4. 在 API 层补鉴权与 CSRF
5. 新增回归测试
6. 更新 `docs/` 文档

## 8. 不建议做的事

- 为历史数据默认添加运行时 fallback（优先一次性迁移）
- 在核心 CRUD 内部随意 `commit` 破坏外层事务边界
- 管理写接口漏加 CSRF
- 上传/导入绕过大小与边界校验
