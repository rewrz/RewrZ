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
  - `{ADMIN_PATH}/api/v1/posts/{id}/inline`（列表页内联编辑，只接受白名单元数据字段）
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

1. `Depends(get_current_user)`，或其角色包装 `Depends(require_admin_user)`
2. `verify_csrf_token(request, csrf_token)`

典型头部：
- `X-CSRF-Token: <token>`

全站后台管理接口（动态 `ADMIN_PATH` 下的页面/接口，以及文章快照、格式管理等后台语义的
固定路径接口）统一使用 `Depends(require_admin_user)`：登录态之上还要求
`admin` / `super_admin` 角色，非管理员返回 403。

保持 `Depends(get_current_user)` 的白名单：后台登录/找回密码/重置密码等公开入口、
前台快捷发布与头像等登录态接口、主题实时更新、外部 API Key 接口、匿名公开读取接口。
评论管理等已有函数体 `ensure_admin_user` 校验的接口保持原样，效果等价。

媒体库列表可见全站媒体用于管理，写操作仍仅允许上传者本人。

### 3.2 前台登录态写接口
- 仍可使用固定公共路径
- 但必须要求登录态或 CSRF
- 不得因为前台要用就放开匿名写权限
- 微博前台发布器接口：
  - `POST /api/v1/posts/quick`：发布动态
  - `POST /api/v1/posts/quick/{post_id}`：前台编辑动态，仅作者本人或管理员可用，编辑不重建 slug，原链接保持不变

### 3.3 外部 API
- 使用：
```http
Authorization: Bearer <api_key>
```
- 不使用 Cookie
- 不依赖 CSRF

### 3.4 公开媒体变体接口
- `GET /media/variant/{media_id}/{preset}/{sig}` 服务前台 `<img>`，保持匿名可读，不引入登录校验
- `sig` 是由站点密钥派生的 HMAC-SHA256 稳定签名（无过期时间），生成端统一由
  `build_variant_url` 输出；签名输入为 `media_id:preset:dpr:fmt`，其中 `dpr` / `fmt`
  取 URL 中实际出现的参数值，缺省为空串。签名放在路径段，CDN 仅按路径缓存也不会丢失
- 签名校验在参数白名单之后、查库之前完成：无效签名返回 403 `invalid_signature`；
  `preset` / `dpr` / `fmt` 非法参数返回 400（`invalid_preset` / `invalid_dpr` / `invalid_fmt`）
- 仅「缓存未命中、实际编码」的请求按客户端 IP 节流并受全局并发上限约束，
  超出返回 429 且带 `Retry-After`；缓存命中与内部预热不受限，避免影响正常图片加载
- 旧形态 `GET /media/variant/{media_id}/{preset}`（无签名）不再提供，升级后需刷新
  页面与 CDN 缓存，否则缓存中的旧链接会返回 404
- 更换 `.env` 的 `SECRET_KEY` 会使已缓存的旧签名 URL 失效，运维需同步刷新页面缓存
- 后台缩略图配置只能收窄、不能剔除基础档位：`thumbnail_allowed_dpr` 必须包含 `1`
  （所有 `src` 默认使用），`thumbnail_allowed_fmt` 必须包含 `jpg`
  （媒体库卡片预览固定使用）；否则请求会被 400 拒绝，表现为整站图片不可用。
  `srcset` 生成侧会按 `thumbnail_allowed_dpr` 过滤，不输出被拒绝的倍率

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

### 5.1 后台统计接口

- `{ADMIN_PATH}/api/v1/analytics/summary` 为后台统计页与看板提供聚合快照，需登录、只读。
- 响应允许逐版本新增向后兼容字段，消费方应忽略未知字段，不按字段数量做断言。
- `guard_blocks` 记录应用层最外层拦截构成，单独成维度，不计入 `requests` 与状态码分布；
  Nginx 规则拦截、静态直出与边缘拦截不回源，需以 Nginx / CDN 日志核对。

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
