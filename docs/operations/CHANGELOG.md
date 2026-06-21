# RewrZ 变更记录

本文档只保留当前仍有参考价值的近期变更摘要，不维护已经过时的占位版本号或文档初始化记录。

## 2026-06-21

### 文档与发布流程

- 删除阶段性工作文档 `THEME_EFFECTS_REFACTOR_PLAN_2026-06-08.md`
- 删除阶段性工作文档 `REAL_WORLD_BROWSER_QA_WORKING_2026-05-31.md`
- 清理临时启动脚本与临时日志文件
- 新增 `docs/operations/RELEASE.md` 作为发布包权威手册
- 新增 `scripts/build_release_package.py` 与 `scripts/build_release_package.ps1`

### 前后台近期收口

- 前台时间元信息统一为 `icon + 时间`
- 公开媒体归档不再暴露私密、密码保护与评论可见隐藏块中的媒体
- 后台用户管理补齐分页、角色友好文案与页面密度优化
- 后台安全中心登录审计补齐分页与清理入口

## 2026-05-30

### 认证与后台用户

- 补齐后台登出路由 `/auth/logout`
- 登录令牌写入并校验 `token_version`
- 后台用户管理补齐新增用户、启停、角色、密码重置、强制退出
- 高风险用户管理动作收紧为仅 `super_admin` 可执行

### 登录前找回密码

- 登录页新增“忘记密码”入口
- 新增找回密码页与重置密码页
- 新增一次性密码重置令牌与过期时间
- 重置成功后自动失效旧登录态
- 未配置 SMTP 时写入 `data/logs/password_reset_debug.log` 作为开发调试投递

### 路由与接口边界

- 后台动态路由继续集中到 `rewrz/api/admin_routes.py`
- 外部集成 API 与后台管理 API 的边界保持分离

### 数据库与迁移

- 修复 SQLite 上 Alembic 迁移对 `dict` 直接绑定的问题
- 修复 SQLite 上 `ALTER COLUMN DROP DEFAULT` 不兼容的问题
- 新增用户找回密码相关字段迁移

### UI

- 登录页改为黑色半透明毛玻璃风格
- 默认品牌标识改为 `R` 黑 / `Z` 白
- 找回密码页与重置密码页统一到登录页同一视觉语言
