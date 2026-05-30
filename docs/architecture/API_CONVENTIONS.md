# RewrZ API 约定

本文档用于统一 API 分层、路径、鉴权规则与新增接口流程。

## 1. API 分层模型

RewrZ 当前 API 分为四层：

### 1.1 前台公共 API
- 固定公共路径
- 服务匿名读取或前台页面消费
- 例如搜索、RSS、公开 SEO、主题读取/同步

### 1.2 前台登录态 API
- 固定公共路径
- 服务前台作者操作
- 仍要求登录态或 CSRF
- 例如前台快捷微博发帖、前台快捷媒体上传

### 1.3 外部集成 API
- 固定前缀：`/api/external/v1`
- 面向第三方系统、APP、自动化工具
- 使用 API Key Bearer 鉴权
- 不复用后台路径

### 1.4 后台管理 API
- 挂载在 `ADMIN_PATH` 下
- 仅服务后台管理台
- 写操作默认要求登录 + CSRF

## 2. 路径与版本约定

### 2.1 公共路径
- 前台可公开能力保持固定公共路径
- 不因为“不是后台路径”就自动判定为安全问题

### 2.2 后台路径
- 后台管理接口保持在 `ADMIN_PATH` 下，例如：
  - `{ADMIN_PATH}/api/v1/media`
  - `{ADMIN_PATH}/api/v1/posts/{id}`
  - `{ADMIN_PATH}/api/v1/api-keys`

### 2.3 外部 API 路径
- 外部系统统一使用：
  - `/api/external/v1/...`

### 2.4 旧 `/api` 别名
- 仅少量前台公共/前台登录态接口仍保留 `/api/...` 旧别名
- `ADMIN_PATH` 下后台内部接口默认只保留 `/api/v1/...`
- 新增外部 API 不再增加旧 `/api` 镜像别名

## 3. 鉴权规则

### 3.1 后台写接口
以下两项缺一不可：

1. `Depends(get_current_user)`
2. `verify_csrf_token(request, csrf_token)`

典型头部：
- `X-CSRF-Token: <token>`

### 3.2 前台登录态写接口
- 仍可使用固定公共路径
- 但必须要求登录态或 CSRF
- 不得因为前台要用就放开匿名写权限

### 3.3 外部 API
- 使用：
```http
Authorization: Bearer <api_key>
```
- 不使用 Cookie
- 不依赖 CSRF

## 4. API Key 约定

### 4.1 轻量等级制

当前默认 4 个等级：

- `read_only`
- `writer`
- `publisher`
- `manager`

### 4.2 设计原则

- 不做复杂 RBAC
- 不做多租户组织模型
- 不做可视化自由拼装 scope 编辑器
- 权限等级到能力的映射固定写在服务端

### 4.3 后台管理范围

后台当前只需提供：
- 创建
- 列表
- 启停
- 轮换
- 删除
- 查看最后使用时间和最后来源 IP

## 5. 响应与错误约定

- 成功响应优先返回清晰 JSON
- 失败统一抛出 `HTTPException`
- 项目内错误信息默认使用中文

外部 API 当前统一约定：
- 单对象成功：
```json
{"success": true, "data": {...}}
```
- 列表成功：
```json
{"success": true, "items": [...], "pagination": {"page": 1, "per_page": 20, "count": 2, "has_next": false}}
```
- 删除成功：
```json
{"success": true}
```
- 错误响应：
```json
{"error": {"code": "VALIDATION_ERROR", "message": "请求参数验证失败", "status_code": 422}}
```

分页与错误契约：
- 列表端点支持 `page`、`per_page`
- `page` 最小为 `1`
- `per_page` 范围为 `1..100`
- 对不存在对象返回 `404`
- 对禁用、过期、错误或缺失 Key 返回 `401`
- 对权限不足返回 `403`
- 对非法参数返回 `422`

## 6. 新增接口 Checklist

新增接口前后至少完成：

1. 确认接口属于哪一层 API
2. 确认路径命名与版本策略
3. 确认鉴权模型
4. 确认参数校验与响应结构
5. 确认 CRUD 事务边界
6. 补齐回归测试
7. 更新相关文档

## 7. 禁止事项

- 不把所有 API 都收进 `ADMIN_PATH`
- 不把前台自用 API 误判成安全问题
- 不直接把后台管理 API 暴露给外部系统
- 不为了兼容历史接口无限增加运行时 fallback
