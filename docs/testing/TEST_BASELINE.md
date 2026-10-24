# RewrZ 测试基线

本文档只记录当前已重新验证过的测试基线，不保留已失效的历史耗时或旧轮次分析。

## 1. 当前收集基线

最近一次重新验证结果：

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

- `403 tests collected in 1.24s`

## 2. 当前已验证的专项回归

### 2.1 忘记密码链路

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_auth_password_reset.py -q
```

- `4 passed`

覆盖点：

- 登录页存在忘记密码入口
- 找回密码请求不泄露未知账户存在性
- 调试投递日志可生成一次性重置链接
- 重置成功后旧登录态失效、新密码可登录

### 2.2 后台用户管理与安全边界

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_users_admin.py tests\test_security_hardening.py tests\test_api_versioning.py -q
```

- `43 passed`

覆盖点：

- 后台用户新增、启停、角色调整、密码重置、强制退出
- CSRF 与登录要求
- 公开 API / 外部 API / 后台 API 路径边界

### 2.3 API Key 与后台仪表盘

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_api_keys_admin.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_admin_dashboard.py -q
```

- `2 passed`
- `2 passed`

### 2.4 前台可见性、媒体归档与后台用户管理

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_users_admin.py tests\test_media_attachments.py tests\test_content_access_and_archives.py -q
```

- `32 passed`

覆盖点：

- 后台用户分页、角色文案、最近活动摘要与管理动作
- 评论可见隐藏块中的媒体不进入公开摘要
- 公开媒体归档不暴露私密、密码保护与未公开内容

### 2.5 访问统计与页面浏览上报

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_traffic_classifier.py tests\test_traffic_analytics_buffer.py tests\test_analytics_api.py -q
```

- `36 passed`

覆盖点：

- 请求分类互斥、来源/UTM 解析、爬虫与可疑来源识别
- 缓冲刷写、失败回填、保留期清理与清空令牌
- 统计页、摘要、实时片段、仪表盘摘要与设置/清空的登录与 CSRF 边界
- beacon 同源校验、2KB 限长、单 IP 限频、后台路径与爬虫拒绝，且不重复计入回源请求

### 2.6 全量回归

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- `403 passed in 410.21s`

## 3. 使用规则

- 文档中若要写“全量测试通过”或“全量耗时基线”，必须先重新实测，再更新此文件
- 若只验证了专项测试，只记录专项测试，不推断为全量结论
- 过时的测试数量、耗时、慢测诊断过程不再在此长期保留
