# RewrZ 外部接入与 APP 开发指南

本文档说明当前 APP / 第三方系统应如何接入 RewrZ。

## 1. 当前接口模型

RewrZ 当前接口模型分为四层：

1. 前台公共 API
- 固定公共路径
- 服务匿名读取或前台页面消费

2. 前台登录态 API
- 固定公共路径
- 继续要求登录态或 CSRF
- 服务前台作者自助操作

3. 外部集成 API
- 固定前缀：`/api/external/v1`
- 面向 APP、自动化工具、第三方系统
- 使用 API Key Bearer 鉴权

4. 后台管理 API
- 挂载在 `ADMIN_PATH`
- 只服务后台管理台

## 2. 为什么不直接复用后台管理 API

后台管理 API 的设计目标仍然是 Web 管理台：
- 认证依赖 Cookie
- 写操作依赖 CSRF
- 管理路径依赖 `ADMIN_PATH`

这套模型适合后台 Web，但不适合直接给外部系统或 APP 使用。

因此，当前推荐做法不是暴露后台管理 API，而是使用独立的外部 API 平面。

## 3. 外部 API 接入方式

### 3.1 认证方式

- 请求头：
```http
Authorization: Bearer <api_key>
```

- API Key 由后台创建和管理
- 明文 Key 只在创建或轮换时展示一次
- 数据库仅保存哈希，不保存明文

### 3.2 轻量权限等级

当前默认提供 4 个等级：

- `read_only`
  - 只读内容读取
- `writer`
  - 可创建/更新草稿与上传媒体
- `publisher`
  - 包含发布能力
- `manager`
  - 包含删除与完整内容管理能力

当前不提供复杂的可视化 scope 编辑器，避免系统膨胀。

## 4. 当前外部 API

### 4.1 读接口

- `GET /api/external/v1/posts`
- `GET /api/external/v1/posts/{id}`
- `GET /api/external/v1/pages`
- `GET /api/external/v1/pages/{id}`
- `GET /api/external/v1/categories`
- `GET /api/external/v1/tags`

列表接口当前支持：
- `page`
- `per_page`

### 4.2 写接口

- `POST /api/external/v1/posts`
- `PATCH /api/external/v1/posts/{id}`
- `DELETE /api/external/v1/posts/{id}`
- `POST /api/external/v1/pages`
- `PATCH /api/external/v1/pages/{id}`
- `DELETE /api/external/v1/pages/{id}`
- `POST /api/external/v1/media`

当前稳定边界：
- 开放：文章、页面、分类列表、标签列表、媒体上传
- 不开放：导入导出、系统设置、评论审核、安全中心、主题后台配置、备份恢复

返回契约摘要：
- 单对象：`{"success": true, "data": {...}}`
- 列表：`{"success": true, "items": [...], "pagination": {...}}`
- 删除：`{"success": true}`
- 错误：`{"error": {"code": "...", "message": "...", "status_code": 4xx/5xx}}`

## 5. APP 接入建议

如果是你自己控制的 APP 或自动化工具，首选直接接入 `/api/external/v1`。

适合直接接入的情况：
- 自建客户端
- 自建发布工具
- 自动化同步脚本
- 第三方内容管理面板

以下场景仍可考虑单独加 BFF：
- 需要多系统聚合
- 需要租户化隔离
- 需要复杂配额与风控
- 需要统一 APP 网关策略

也就是说，BFF 现在不再是唯一推荐路径，而是复杂场景的增强选项。

## 6. 安全边界

- 不直接把后台管理 API 暴露给 APP 或第三方系统
- 不在外部集成场景使用后台 Cookie
- 不把所有 API 都收进 `ADMIN_PATH`
- 前台自用 API 可以保留公共路径，只要语义上不是后台敏感管理接口

## 7. 当前不对外开放的范围

以下能力暂不纳入首期外部开放范围：

- 导入导出
- 系统设置
- 评论审核
- 安全中心
- 主题后台配置
- 备份恢复

这些能力仍默认属于后台管理面。
