# RewrZ 变更记录

本文档只保留当前仍有参考价值的近期变更摘要，不维护已经过时的占位版本号或文档初始化记录。

## 2026-09-01

### 安全依赖升级

- 修复 GitHub 安全告警涉及的直接依赖，统一升到当前已修复版本：`starlette` 0.52.1 → 1.6.0、`python-multipart` 0.0.20 → 0.0.32、`Pillow` 12.1.1 → 12.3.0、`aiohttp` 3.13.3 → 3.14.3
- 同步处理 Dependabot 待合并项：`bleach` 6.3.0 → 6.4.0、`python-dotenv` 1.2.1 → 1.2.3、`pytest` 9.0.2 → 9.1.1
- `fastapi` 0.133.0 → 0.141.1：Starlette 1.x 是首个稳定大版本，需同步升级 FastAPI 以保证兼容
- 新增 `httpx2` 2.12.0 作为测试依赖：`starlette.testclient` 已改用 httpx2，继续回退到 httpx 会抛出弃用警告，安装后测试无警告输出
- 修复 npm 开发依赖 4 个高危告警（`shell-quote`、`brace-expansion`、`postcss`、`nanoid`），`npm audit` 已归零

### Starlette 1.x 兼容性迁移

- Starlette 1.0 移除了已废弃的 `TemplateResponse(name, context)` 两参数写法，全站 64 处调用统一改为 `TemplateResponse(request, name, context)`
- FastAPI 0.141 起 `include_router` 不再把路由平铺进 `app.routes`，而是包装为 `_IncludedRouter`；测试中的路由收集辅助函数改为递归展开其 `original_router`

## 2026-08-31

### 前端性能与细节打磨

- 字体瘦身：全站正文字体改用系统字体栈（零下载），标题字体替换为 GB2312 常用字集子集化 woff2（8.6MB → 1.15MB，减少 87%）；验证码改用专用字符子集字体（11.8KB，`scripts/build_captcha_font.py` 可重建）
- 修复主题系统双源冲突与性能问题：首屏不再用 JS 预设覆盖服务端主题变量、不再重复重拉 variables.css；`variables.css` 加载失败时才用本地预设兜底
- 修复特效监听器泄漏：23 个画布特效的 window resize 监听统一迁移到 effect-manager 注册/销毁；回到标签页时特效配置无变化不再 stopAll 重启
- 特效系统尊重 `prefers-reduced-motion`（灰度滤镜除外）；脚本加载保留 onerror 兜底
- 修复 `admin/post_snapshots.html` 整文件属性引号被错误转义（`\"`），该页样式与 htmx 实际未生效的问题
- admin 提示条/确认弹窗大面积面板色全部主题变量化，跟随动态主题；语义强调色保留固定色
- 全局打磨层：选区颜色、键盘焦点环（:focus-visible）、主题色滚动条、首帧过渡抑制（js-ready）、`prefers-reduced-motion` 全站兜底
- 资产合并与清理：前后台共用一份 `site-tailwind.css`（删除重复的 admin-tailwind 产物与构建脚本）；删除零引用死文件 `homepage-animations.js`、`reading-progress.js`、`animations.css`、`performance.css`、`anniversary-effects.css`、`multi-format-layout.css`
- `ui-enhancements.js` 清理死分支（.navbar/.timeline-item/.page-loader/.modal Esc），通知消息改文本节点防注入；Ctrl+K 聚焦站内搜索保留
- 修复首页时光轴卡片行级色差：删除 `.timeline-card-shell > div` 的 `!important` 底色规则（壳内每个直接子行被叠加 95% 底色，而标题/摘要不受影响，导致徽标行/标签行/元信息行出现横块）；卡内徽标与标签片底色改透明，整卡回归单一表面
- 修复 `post-detail.css` 中 7 处 `transition` 因引用未定义的 `--easing-smooth` 而整条失效（收敛到已有的 `--ease-in-out`）
- 修正批量改造的副作用：23 个特效文件的 `handleWindowResize` 缩进错位、41 个文件行尾被写成 LF（已统一回 CRLF）

### 安装向导

- 修复初始内容创建不生效的问题：预览与创建共用同一份默认内容定义（`rewrz/core/default_content.py`），结果只统计实际新增，重复提交幂等
- 默认内容类型复用 `content_intents` 权威规则（article/micro/poem），与内容模型现状对齐
- 勾选示例文章时创建一篇已发布的示例文章，并按需自动补齐归属用的首个分类与标签
- 安装向导建库后自动标记 Alembic head，新装站点不再需要（也不应）执行 `alembic upgrade head`

### 部署与依赖

- `requirements.txt` 补齐 `python-multipart`、`itsdangerous`、`alembic`
- Alembic 迁移目标库改为优先读取 `.env` 的 `DATABASE_URL`，`alembic.ini` 仅作兜底
- 静态资源链接统一收口为根相对路径，修复反向代理改端口后静态资源生成跨域绝对地址被浏览器拦截的问题
- 重写一键更新脚本 `update.sh`：更新前自动备份、支持指定标签/提交、迁移、`.env` 重复项检测、服务重启与最小烟测；维护约定见 `AGENTS.md`
- 部署、更新、排障手册与实际流程同步更新（目录示例变量化、Nginx 配置模板修正、迁移与 `.env` 修改方式修正）

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
