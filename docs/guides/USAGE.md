# RewrZ 使用文档

本文档面向站长与运营者，只描述当前有效的运行、部署与日常操作方式。

## 1. 环境要求
- Python 3.10+
- 建议 512MB 以上内存
- Linux/Windows/macOS 均可运行（生产推荐 Linux）
- 生产部署默认不要求安装 Node；仓库已提交编译后的前端 CSS 产物

## 2. 本地运行（开发/测试）

### 2.1 启动步骤
```bash
git clone https://github.com/RewrZ/RewrZ.git
cd RewrZ
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
./.venv/Scripts/python.exe -m uvicorn rewrz.main:app --host 127.0.0.1 --port 8001 --reload
```

Linux/macOS 可改为：
```bash
.venv/bin/python -m uvicorn rewrz.main:app --host 127.0.0.1 --port 8001 --reload
```

如果你要修改站点样式或模板中的 Tailwind 类名，再额外执行：
```bash
npm install
npm run build:css
```

启动后访问：

- 未安装：`http://127.0.0.1:8001/installer`
- 已安装：`http://127.0.0.1:8001/<你的 ADMIN_PATH>/login`

### 2.2 安装向导流程
1. 环境检查
2. 数据库初始化
3. 管理员创建
4. 站点配置
5. 后台路径配置
6. 完成安装并进入登录页

安装完成后会生成 `.env`（包含 `SECRET_KEY`、`DATABASE_URL`、`ADMIN_PATH` 等）。

首次安装的重要约束：
- 不要在进入 `/installer` 前手工创建 `.env`
- 新站点的 `.env` 应由安装向导生成
- 若后续要补 `COOKIE_SECURE`、`SESSION_HTTPS_ONLY`、SMTP 等生产配置，请在安装完成后再编辑 `.env`

## 3. 线上部署与更新

生产上线请直接看以下两份主文档：
- 首次部署：[`../operations/DEPLOYMENT.md`](../operations/DEPLOYMENT.md)
- 日常更新：[`../operations/UPDATE.md`](../operations/UPDATE.md)
- 发布包生成：[`../operations/RELEASE.md`](../operations/RELEASE.md)

这里仅保留三条不会变的原则：
- 新站点首次上线时，不要预先手工创建 `.env`
- 先完成 `/installer`，再补生产安全项、SMTP 与反向代理
- 上线和更新前后都执行一次 `alembic upgrade head`

## 4. 关键配置

### 4.1 常用环境变量
```env
DATABASE_URL=sqlite:///./data/rewrz.db
SECRET_KEY=请使用高强度随机字符串
ADMIN_PATH=/your-admin-path
MEDIA_UPLOAD_DIR=media_uploads
COOKIE_SECURE=false
SESSION_HTTPS_ONLY=false
```

### 4.2 生产建议
- 强烈建议启用 HTTPS。
- `ADMIN_PATH` 使用难猜测路径，避免默认后台暴露。
- 反向代理场景建议开启：
  - `COOKIE_SECURE=true`
  - `SESSION_HTTPS_ONLY=true`
- 若要启用登录前找回密码邮件投递，还需额外配置 SMTP 环境变量。

## 5. 日常使用

### 5.1 内容发布
- `post_type` 仅支持：`post`（文章）与 `page`（页面）。
- `article/micro/poem` 通过内容意图（formats）管理，不是主类型。

### 5.1.1 后台用户与登录

- 后台用户支持：
  - 登录
  - 登出
  - 忘记密码 / 重置密码
  - 用户启停、角色调整、密码重置、强制退出
- 高风险用户管理动作默认仅允许 `super_admin`

### 5.2 媒体管理
- 支持上传、移动、批量删除、重复文件清理。
- 上传链路采用流式写入并限制文件大小，超限会拒绝。

### 5.3 评论与互动
- 支持评论审核与反垃圾策略。
- 支持点赞/表态等互动能力。

### 5.4 主题与氛围
- 支持主题切换、节日/纪念日氛围配置、主题调度。

### 5.5 数据管理
- 支持导出 JSON、备份包。
- 支持导入 RewrZ JSON、WordPress WXR、备份 ZIP。

### 5.6 外部系统接入

- 外部系统统一使用 `/api/external/v1/...`
- 认证方式为 `Authorization: Bearer <api_key>`
- API Key 在后台管理台创建、启停、轮换与删除

## 6. 安全操作建议
- 仅通过 HTTPS 暴露后台。
- 对后台路径做 IP 白名单（Nginx/网关层）。
- 定期执行数据导出与备份恢复演练。
- 监控登录失败与异常请求。

## 7. 升级与回滚
- 升级前：先备份数据库和 `media_uploads/`。
- 升级后：优先在测试环境验证导入、上传、发布流程。
- 若需回滚：还原数据库与媒体目录，再恢复旧版本代码。

## 8. 常见问题

### Q1：访问 `/installer` 自动跳转？
系统已判定当前实例安装完成时，`/installer` 会自动跳转，这是正常行为。

### Q2：为什么后台地址找不到？
请检查 `.env` 中 `ADMIN_PATH` 配置。

### Q3：上传失败提示大小超限？
检查后台媒体设置中的上传上限与反向代理上传限制（`client_max_body_size`）。

### Q4：导入备份失败？
备份 ZIP 会进行路径/压缩比/体积安全校验，非法包会被拒绝。

### Q5：宝塔下出现 502 Bad Gateway？
通常是 Python 项目进程没起来或端口不一致，按顺序检查：
1. 宝塔 Python 项目是否正在运行（先重启一次项目）
2. 启动命令是否正确：`.venv/bin/uvicorn rewrz.main:app --host 127.0.0.1 --port 8000 --workers 2`
3. Nginx 反代端口是否和 Python 项目一致（例如都为 `8000`）
4. 项目日志是否报错（缺依赖、权限不足、`.env` 配置错误）

### Q6：宝塔部署后页面可访问，但样式/图片 404？
优先检查以下项：
1. 是否在正确项目目录启动（必须包含 `rewrz/static`）
2. `.env` 中 `MEDIA_UPLOAD_DIR` 是否指向真实目录
3. 项目目录和媒体目录权限是否允许运行用户读取
4. 修改后重启 Python 项目和 Nginx

### Q7：登录后立即掉线或反复跳回登录页？
常见原因是 Cookie 安全配置与访问协议不匹配：
- 如果你还在 HTTP 访问，不要启用 `COOKIE_SECURE=true`
- 如果你已启用 HTTPS，建议：
  - `COOKIE_SECURE=true`
  - `SESSION_HTTPS_ONLY=true`
- 反向代理需传递 `X-Forwarded-Proto` 请求头

### Q8：忘记密码申请后没有收到邮件？
- 先确认是否已配置 SMTP：
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USERNAME`
  - `SMTP_PASSWORD`
  - `SMTP_FROM`
- 开发环境若未配置 SMTP，系统会将重置链接写入：
  - `data/logs/password_reset_debug.log`

### Q9：出现 `database is locked`（SQLite 锁库）怎么办？
1. 先确认没有多个重复实例在同时写同一个 SQLite 文件
2. 减少并发写入压力（尤其导入/批量操作时）
3. 保持数据库文件在本地磁盘，不要放在高延迟网络存储
4. 若长期高并发写入，建议迁移到 PostgreSQL

## 9. 文档入口
- 文档中心：[`docs/INDEX.md`](../INDEX.md)
- 项目总览：[`README.md`](../../README.md)
- 开发文档：[`DEVELOPMENT.md`](DEVELOPMENT.md)
- 生产部署：[`../operations/DEPLOYMENT.md`](../operations/DEPLOYMENT.md)
- 生产更新：[`../operations/UPDATE.md`](../operations/UPDATE.md)
