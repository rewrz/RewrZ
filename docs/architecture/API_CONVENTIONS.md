# RewrZ API 约定

本文档用于统一 API 设计、鉴权规则与新增接口流程。

## 1. 路径与版本约定

### 1.1 版本路径
- 新接口优先使用 `/api/v1/...`
- 兼容阶段可同时保留 `/api/...`（同语义旧路径）

### 1.2 后台路径
- 管理后台相关接口通常挂载在 `ADMIN_PATH` 下，例如：
  - `{ADMIN_PATH}/api/v1/media`
  - `{ADMIN_PATH}/api/v1/posts/{id}`

### 1.3 公共路径
- 前台可公开接口保持固定公共路径（如搜索、RSS、反应、公开 SEO 等）。

## 2. 鉴权与 CSRF 规则

### 2.1 后台写接口（强制）
以下两项缺一不可：
1. 登录依赖：`Depends(get_current_user)`
2. CSRF 校验：`verify_csrf_token(request, csrf_token)`

典型头部：
- `X-CSRF-Token: <token>`

### 2.2 只读接口
- 可按业务选择是否开放匿名访问。
- 若是后台敏感数据，即使只读也建议鉴权。

## 3. API 分层职责

- `api/*`：请求解析、鉴权、参数校验、响应拼装
- `crud/*`：数据库读写与事务控制
- `core/*`：跨模块能力（安全、导入导出、媒体处理等）

不要把复杂业务逻辑长期堆在路由层。

## 4. 响应与错误约定

- 成功响应可使用：
  - 标准对象：`{"success": true, ...}`
  - 或直接返回 schema（保持现有模块一致）
- 失败统一抛出 `HTTPException`，错误信息以中文为主。

## 5. 新增 API 清单（Checklist）

新增接口前后至少完成：
1. 路径命名与版本策略确认（是否需要 `/api/v1` + `/api` 双路径）
2. 鉴权与 CSRF 策略确认
3. Schema 与参数校验
4. CRUD 事务边界确认（避免内层随意 commit）
5. 回归测试补齐（正向 + 异常 + 权限）
6. 文档更新（`CHANGELOG` / `INDEX` / 对应专题）

## 6. 面向 APP 的建议

RewrZ 已有较多 API，可支持独立客户端开发，但需注意：
- 当前后台写能力以 Cookie + CSRF 为主，天然偏 Web 场景。
- 若做移动端/桌面端 APP，建议新增“应用专用鉴权层”（如 token/BFF）。

详见：[`API_APP.md`](API_APP.md)

