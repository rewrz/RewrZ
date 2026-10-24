# RewrZ 生产部署手册

本文档面向首次上线生产环境的站点维护者，只保留当前有效流程。

## 1. 适用范围

- 推荐环境：Linux + `systemd` + Nginx + HTTPS
- 默认数据库：SQLite
- 默认媒体目录：`media_uploads/`
- 默认原则：单实例运行，同一份 SQLite 不允许多实例并发写入

## 2. 上线前准备

服务器至少准备：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git
```

建议同时确认：
- 域名已解析到目标服务器
- 计划使用的运行用户已确定（例如 `www-data`）
- 站点目录使用本地磁盘，不放网络盘

### 关于本文中的示例路径

本文统一使用 `/srv/rewrz` 作为部署目录示例。
实际部署时请**全局替换**为你自己的目录（放在 `/srv`、`/opt` 或用户主目录下均可），
至少包括：systemd 的 `WorkingDirectory` 与 `ExecStart`、Nginx 的 `alias`、
以及所有 `cd` 目标路径。下文不再逐处重复提示。

## 3. 拉取代码与安装依赖

如果你不想在生产机直接执行 `git clone`，也可以先在本地生成干净发布包，再上传到服务器解压：

- 发布包生成手册：[`RELEASE.md`](RELEASE.md)

默认方式仍建议使用 Git 仓库拉取：

```bash
sudo mkdir -p /srv
cd /srv
sudo git clone https://github.com/RewrZ/RewrZ.git rewrz
sudo chown -R $USER:$USER /srv/rewrz
cd /srv/rewrz

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

说明：
- 仓库已提交编译后的 CSS 产物，纯部署通常不需要安装 Node
- 只有你准备修改前端样式时，才需要额外执行 `npm install` 与 `npm run build:css`

## 4. 首次安装

首次安装的关键原则：
- 不要先手工创建 `.env`
- 让安装向导生成 `.env`
- 安装完成后，再补生产安全配置

先直接启动一次应用，供安装向导使用：

```bash
cd /srv/rewrz
source .venv/bin/activate
uvicorn rewrz.main:app --host 127.0.0.1 --port 8000
```

然后访问：

- `http://你的域名/installer`
- 或 `http://服务器IP/installer`

按向导完成以下步骤：
1. 环境检查
2. 数据库初始化
3. 管理员创建
4. 站点配置
5. 后台路径配置
6. 初始内容设置（默认分类、标签、内容类型与示例文章，可跳过）
7. 完成安装

安装完成后会生成 `.env`，其中至少包含：
- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_PATH`
- `MEDIA_UPLOAD_DIR`
- `SITE_TIMEZONE`（站点展示时区，默认 `Asia/Shanghai`；数据库统一存 UTC）

## 5. 安装完成后的立即处理

停止刚才的临时前台进程后，先补两件事：

### 5.1 数据库迁移：新装站点不需要执行

安装向导在建库时已经把新库标记为 Alembic 最新版本（`alembic stamp head`），
因此**全新安装的站点不要再执行 `alembic upgrade head`**，
否则会重复执行建表迁移并报错。

只有升级已有站点才需要迁移，见 [`UPDATE.md`](UPDATE.md)。

如果要确认当前版本状态，可执行：

```bash
cd /srv/rewrz
source .venv/bin/activate
alembic current
```

说明：迁移目标库来自 `.env` 的 `DATABASE_URL`，`alembic.ini` 里的
`sqlalchemy.url` 只是兜底值，不需要手工修改。

### 5.2 补生产环境配置

编辑 `/srv/rewrz/.env`。

Cookie 安全标志无需任何配置：`Secure` 按每个请求的实际协议自动判定
（识别 `X-Forwarded-Proto` 与请求 scheme），HTTP、HTTPS 与后续新增反向代理
都不需要修改配置或重启服务。

唯一例外：反向代理**不**传递 `X-Forwarded-Proto`、或你希望强制所有 Cookie
携带 `Secure` 时，才手动设置：

```env
COOKIE_SECURE=true
```

注意：HTTP 直连场景下设置 `COOKIE_SECURE=true` 会导致登录后立即掉线。

如需邮件能力，再补：

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-user
SMTP_PASSWORD=your-password
SMTP_FROM=notify@example.com
```

不要使用 `echo >> .env` 直接追加，重复键会导致配置歧义（后写的值覆盖前面的）。
请先把整行删除再写入，保证每个键只出现一次、可重复执行。

建议同时核对：
- `ADMIN_PATH` 是否为安装向导生成的隐藏后台路径
- `DATABASE_URL` 是否指向你真正要使用的生产库
- `MEDIA_UPLOAD_DIR` 是否与实际媒体目录一致
- `SITE_TIMEZONE` 是否为站点所在时区（IANA 名称，例如 `Asia/Shanghai`、`Asia/Tokyo`、`America/Toronto`）

数据库连接池与 SQLite 并发参数均有安全默认值，不配置也可直接运行。
SQLite 站点默认 10 + 10 个溢出连接，PostgreSQL 等网络数据库默认 10 + 20。
连接按需创建：空闲时不会占满，只有高并发时才扩展；SQLite 每个连接的页缓存
由 `SQLITE_CACHE_SIZE_KIB` 限死，因此放大连接池不会带来无界内存增长：

```env
# 每个 worker 进程独立的连接池；SQLite 默认 10+10
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=10
# 以下两项仅对网络数据库生效；本地 SQLite 默认关闭预检查与连接回收
DB_POOL_RECYCLE=1800
DB_POOL_PRE_PING=true
# SQLite 默认启用 WAL，并将写锁等待上限提高到 30 秒
SQLITE_BUSY_TIMEOUT_MS=30000
SQLITE_JOURNAL_MODE=WAL
# 每连接页缓存上限（KiB），默认 1MB；20 个连接最坏约 20MB
SQLITE_CACHE_SIZE_KIB=1024
# WAL 下 synchronous=NORMAL 可减少每次提交的 fsync，提升写吞吐；
# 断电时可能丢失最后少量事务，博客场景可接受
SQLITE_SYNCHRONOUS=NORMAL
```

注意：多 worker 时连接池上限按进程分别计算，生产库为 PostgreSQL 时
总连接数约为 `workers * (DB_POOL_SIZE + DB_MAX_OVERFLOW)`，请确保不超过
数据库实例的连接上限。SQLite 站点不要为了追求并发盲目调大 worker 数；
突发大并发应优先靠页面与图片缓存卸载到边缘，而不是继续堆 worker。

如果服务器内存特别紧张（低于 512MB），可显式写成 `DB_POOL_SIZE=8`、
`DB_MAX_OVERFLOW=8`；512MB 及以上保持默认 10+10 即可。

首页、分类归档与标签归档由两层缓存承载：

- 进程内缓存：保存渲染后的整页 HTML，默认保留 20 秒，匿名 GET 命中后不再查询
  数据库与渲染模板；新建、编辑、删除文章会立即清空缓存。总预算约 8MB。
- 边缘缓存：匿名列表页响应带 `Cache-Control: public, max-age=0, s-maxage=20`，
  且不创建会话，因此没有 `Set-Cookie` 与 `Vary: Cookie`，Cloudflare 等 CDN
  可以直接缓存整页 HTML。浏览器侧始终为 `max-age=0`，不会拿到过期的页面。
  已登录用户、HTMX 分页片段与错误页的响应为 `private, no-store`，即使 CDN
  启用了 Cache Everything 也不会误缓存。带游客主题 Cookie 的请求同样返回
  `private, no-store`：CDN 缓存键只有 URL，无法区分主题，缓存后会串主题。

匿名列表页不含评论等受保护表单，游客主题偏好由浏览器本地 Cookie 维护，所以不写
CSRF 会话。多 worker 部署时各进程缓存互相独立，发布后的最长可见延迟仍为 20 秒。

### 5.3 SQLite 的并发边界

SQLite 适合单实例博客，不适合作为横向扩容的共享数据库：

- 同一份 SQLite 文件只允许一个应用实例写入。不要在多台机器、多个容器或多个
  worker 之间共享同一数据库文件，也不要把数据库放到 NFS、SMB 等网络盘上。
- WAL 模式下读可以并发，写仍然串行；写事务会排队，`SQLITE_BUSY_TIMEOUT_MS`
  只是等待上限，不会提升写入吞吐。
- 每个 worker 进程都会独立创建连接池、整页缓存和封面预取线程。SQLite 站点
  增加 worker 只会放大内存占用与写锁竞争，不能提升写入能力。
- 需要多 worker、多实例读写或持续高并发写入时，先迁移到 PostgreSQL，见 5.4。

### 5.4 迁移到 PostgreSQL

适用场景：需要多 worker、多实例读写同一数据库，或写入量已经明显受 SQLite
单写者限制。

这是第 4 节安装向导流程的唯一例外：安装向导只支持 SQLite，PostgreSQL 站点
需要手工准备数据库和 `.env`，不能再走 `/installer`。

#### 1. 安装驱动

`requirements.txt` 不包含 PostgreSQL 驱动，需要在虚拟环境中单独安装：

```bash
cd /srv/rewrz
source .venv/bin/activate
pip install "psycopg[binary]"
```

#### 2. 创建数据库与账号

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE rewrz LOGIN PASSWORD '替换为强密码';
CREATE DATABASE rewrz OWNER rewrz ENCODING 'UTF8';
-- PostgreSQL 15 及以上还需要授权 public schema
\c rewrz
GRANT ALL ON SCHEMA public TO rewrz;
\q
```

#### 3. 写入 `.env`

先备份现有 `.env`，再按下面的键完整写入，保证每个键只出现一次：

```env
DATABASE_URL=postgresql+psycopg://rewrz:密码@127.0.0.1:5432/rewrz
SECRET_KEY=...
ADMIN_PATH=...
MEDIA_UPLOAD_DIR=media_uploads
SITE_URL=https://example.com
ALLOWED_HOSTS=example.com,127.0.0.1
SITE_TIMEZONE=Asia/Shanghai
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=10
DB_POOL_RECYCLE=1800
DB_POOL_PRE_PING=true
```

- 密码包含 `@`、`/`、`:` 等字符时必须做 URL 编码。
- `DATABASE_URL` 必须带 `+psycopg`，否则 SQLAlchemy 会去寻找未安装的 `psycopg2`。
- SQLite 专属参数（`SQLITE_*`）在 PostgreSQL 下不生效，可以直接删除。
- `SECRET_KEY` 可用 `openssl rand -hex 32` 重新生成；更换后所有旧登录会话失效。

#### 4. 首次启动建表

```bash
sudo systemctl restart rewrz
sudo journalctl -u rewrz -n 50 --no-pager
```

空库首次启动时，应用会通过 `create_all_tables()` 创建当前模型对应的表。
不要执行 `alembic upgrade head`：生产库没有迁移基线，会重复建表并报错。

#### 5. 创建管理员并导入数据

完整备份包不包含用户表，新库需要先创建管理员，再导入内容：

```bash
cd /srv/rewrz
source .venv/bin/activate
python - <<'PY'
import getpass
from rewrz.core.database import db_manager
from rewrz.crud import user as crud_user

session = db_manager.get_session()
if session is None:
    raise SystemExit("数据库未初始化，请先确认 .env 中的 DATABASE_URL 并成功启动一次服务")
try:
    username = input("管理员用户名: ").strip()
    email = input("管理员邮箱: ").strip()
    password = getpass.getpass("管理员密码: ")
    crud_user.create_admin_user(session, username=username, email=email, password=password)
    print("管理员已创建")
finally:
    session.close()
PY
```

先在旧站（SQLite）后台导出完整备份 ZIP：后台 → 数据管理 → 导出备份包。
备份包包含内容 JSON 与 `media` 文件，不包含管理员账号、SMTP 密码等敏感配置。

然后在新站登录后台导入该 ZIP。导入会写回文章、分类、标签、评论、媒体记录与
站点设置，并恢复媒体文件。

如果媒体目录超过导入接口 100MB 上限，先用 `rsync` 同步 `media_uploads/`，
再在数据管理中只导入 JSON 文件。

#### 6. 迁移后验收

```bash
curl -I https://example.com/
curl -I https://example.com/<你的ADMIN_PATH>/login
```

- 首页、分类/标签归档与分页正常
- 文章详情、评论与隐藏内容解锁正常
- 媒体图片经 `/media/variant/...` 正常返回
- 后台可登录，设置、媒体库与备份导出可用

#### 7. 回滚

迁移前保留旧 SQLite 库、旧 `.env` 与媒体目录。需要回滚时：

```bash
sudo systemctl stop rewrz
cp .env.sqlite.backup .env
# 如需恢复数据，再用 SQLite 备份覆盖 data/rewrz.db
sudo systemctl start rewrz
```

PostgreSQL 运行期间产生的新内容不会自动回到 SQLite，回滚前应先导出备份包。

## 6. 配置 systemd

以下步骤全部需要 `sudo` 权限。`/etc/systemd/system/` 普通用户不可写，
如果无法直接写入，可先写到 `/tmp/rewrz.service`，再用 `sudo cp` 移动过去。

创建 `/etc/systemd/system/rewrz.service`：

```ini
[Unit]
Description=RewrZ Blog Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/srv/rewrz
Environment=PYTHONUNBUFFERED=1
Environment=MALLOC_ARENA_MAX=2
ExecStart=/srv/rewrz/.venv/bin/uvicorn rewrz.main:app --host 127.0.0.1 --port 8000 --workers 1 --timeout-graceful-shutdown 10
Restart=always
RestartSec=3
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

`--timeout-graceful-shutdown 10` 让 Uvicorn 在重启时最多等待 10 秒处理完
存量请求；`TimeoutStopSec=30` 给 systemd 留出应用退出和进程回收时间。
两者需同时保留，避免更新时直接强杀进程。

`MALLOC_ARENA_MAX=2` 限制 glibc 线程内存池数量，避免图片处理等
瞬时峰值过后 RSS 长期停留在高位。

### 6.1 512MB 小内存服务器

项目以 512MB 内存 VPS 可运行为目标，小内存机器请使用 `--workers 1`。
SQLite 站点也只能单实例写入；需要多 worker 时先按 5.4 迁移到 PostgreSQL，
再按 6.2 控制进程数与连接数，不要直接堆 worker。

在 `[Service]` 段落中额外加入 cgroup 限制，让超限时只重启应用进程，
而不是让内核把整机拖入 OOM：

```ini
MemoryHigh=350M
MemoryMax=450M
```

同时建议至少配置 1GB swap：

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

如果站点有较高访问量，或需要同时运行数据库、缓存等其它服务，
建议把内存升到 1GB 以上；1GB 内存也建议保持 `--workers 1`。

然后执行：

```bash
sudo chown -R www-data:www-data /srv/rewrz
sudo systemctl daemon-reload
sudo systemctl enable rewrz
sudo systemctl start rewrz
sudo systemctl status rewrz
```

### 6.2 多 worker 部署（仅 PostgreSQL）

SQLite 站点固定 `--workers 1`。数据库切换为 PostgreSQL 后，才考虑增加 worker：

```ini
ExecStart=/srv/rewrz/.venv/bin/uvicorn rewrz.main:app --host 127.0.0.1 --port 8000 --workers 4 --timeout-graceful-shutdown 10
```

内存预算：

- 每个 worker 都是独立 Python 进程，空闲内存约 120–200MB，图片处理峰值更高
- 512MB 机器不要多 worker；1GB 建议最多 2 个；2GB 及以上再考虑 4 个
- 每个 worker 建议预留 250MB 以上，并保留 `MemoryHigh` / `MemoryMax` 与 swap

数据库连接预算：

- 每个 worker 各自持有连接池，总连接数约为
  `workers * (DB_POOL_SIZE + DB_MAX_OVERFLOW)`
- 总连接数建议不超过 PostgreSQL `max_connections` 的 70%，给迁移、备份与运维留余量
- 例如 `max_connections=100`、4 个 worker 时，设置 `DB_POOL_SIZE=10`、
  `DB_MAX_OVERFLOW=5`，总量为 60

多 worker 后仍然按进程隔离的行为：

- 匿名列表页整页缓存各自独立，发布后的最长可见延迟仍为 20 秒
- 封面预取并发上限按进程计算，`N` 个 worker 最坏同时有 `2N` 个预取线程
- 定时任务调度器在每个 worker 中各跑一份，默认任务均为幂等清理；
  不要新增依赖“只执行一次”的重写入定时任务

## 7. 配置 Nginx

### 7.1 先看端口是否被占用

`80` / `443` 常被 Docker、宝塔或已有 Web 服务占用，配置前先确认：

```bash
sudo ss -tlnp | grep -E ':80|:443'
```

如果被占用，二选一：
- 停掉占用进程
- 改用其他端口（例如 `listen 8080;`），并保持与用户实际访问入口一致

### 7.2 创建站点配置

创建 `/etc/nginx/sites-available/rewrz.conf`（需要 `sudo`）：

```nginx
server {
    listen 80;
    server_name example.com;

    client_max_body_size 100m;

    # 静态资源由 Nginx 直出，减轻应用层压力
    location /static/ {
        alias /srv/rewrz/rewrz/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 媒体目录不要在这里直出：/media/variant/... 是动态缩略图路由，
    # 被静态 location 抢先匹配后会导致缩略图 404。
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        # 传原始 Host（含端口），避免应用按错误的入口生成站内地址
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# 未知 Host 兜底：避免任意 Host 落到 RewrZ 站点，污染密码重置链接与日志
server {
    listen 80 default_server;
    listen 443 ssl default_server;
    server_name _;

    # certbot 执行后把这里替换为实际证书路径
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    return 444;
}
```

说明：
- `alias` 路径中的 `/srv/rewrz` 要替换成你的实际部署目录
- 文中出现的 `$http_host` 是 Nginx 变量，不是 shell 变量，不要转义
- 首次配置时如果证书尚未签发，可先只保留 `listen 80 default_server;`，执行完第 8 节的 certbot 后再补 `443 ssl default_server` 两行
- 建议在 `.env` 中同时配置 `ALLOWED_HOSTS=example.com,127.0.0.1`，应用层会拒绝不匹配的 Host 头；
  其中 `127.0.0.1` 用于保留 `update.sh` 的本机健康检查

### 7.3 Cloudflare 回源场景

如果站点经 Cloudflare 代理（橙云）回源，源站看到的直连地址是 Cloudflare 节点。
完整方案（UFW 仅放行 Cloudflare 官方网段、每 15 分钟自动同步、Nginx 还原真实 IP）
见 [`CLOUDFLARE_ORIGIN.md`](CLOUDFLARE_ORIGIN.md)。

只做 Nginx 侧时，至少满足三点：

- `set_real_ip_from` 覆盖 Cloudflare 官方全部网段并定期同步，不要长期手写固定几段
- `real_ip_header CF-Connecting-IP;`
- 站点配置中 `X-Forwarded-For` 改为 `$remote_addr`（覆盖而不是追加），
  避免客户端伪造链进入应用审计

`.env` 中的 `TRUSTED_PROXIES` 保持默认 `127.0.0.1,::1`：Nginx 已完成真实 IP 还原，
应用只信任本机 Nginx，不要把 Cloudflare 网段加进去。

应用已为匿名列表页输出 `Cache-Control: public, max-age=0, s-maxage=20`。
要让 Cloudflare 真正缓存整页 HTML，还需在控制台添加一条 Cache Rule：

- 匹配路径：`/`、`/archives/by-category/*`、`/archives/by-tag/*`
- 当 Cookie 包含 `access_token` 或 `rewrz_theme` 时执行 `Bypass cache`
  （登录态与游客主题变体不能共用同一份缓存）
- 其余请求执行 `Cache Everything`，边缘 TTL 以源站 `s-maxage` 为准

没有这条规则时，Cloudflare 默认只缓存带静态扩展名的资源，HTML 仍每次回源：
功能正常，但拿不到边缘缓存收益。

### 7.4 访问统计与 CDN / 反向代理

后台“访问统计”采用双口径：

- 回源请求：只统计到达源站的动态请求，用于数据库容量、爬虫、可疑来源与状态码判断
- 页面浏览上报：公开页通过 `navigator.sendBeacon` 向 `POST /api/v1/traffic/pageview` 上报，
  用于补全 CDN / 反向代理命中缓存、未回源的浏览；有效访问取两者较大值

要让统计完整，需保证：

- `POST /api/v1/traffic/pageview` 能正常回源，不被 WAF、防火墙或“缓存全部”规则拦截；
  该端点固定返回 `204` + `Cache-Control: no-store`，本身不会被缓存
- 若 CDN 上配置了自定义 Cache Rule / Page Rule，请对 `/api/*` 选择 `Bypass cache`，
  不要把 API 请求纳入整页缓存或改写规则
- 真实 IP 决定 UV 去重与上报限流（单 IP 每分钟最多 120 条）；真实 IP 丢失会导致 UV 偏低，
  多用户被合并到同一边缘 IP 而提前触发限流

`TRUSTED_PROXIES` 按实际拓扑二选一：

- 本文 Nginx + Cloudflare 方案：Nginx 已用 `real_ip` 还原真实 IP，
  保持默认 `127.0.0.1,::1`，不要把 Cloudflare 网段加进去
- CDN / 反向代理直接回源到应用（应用前面没有 Nginx 做真实 IP 还原）：
  必须把回源 IP 或网段写入 `TRUSTED_PROXIES`，否则应用只能看到边缘节点地址

DNT 用户、禁用 JS 的用户与爬虫不会执行上报，这部分由回源 PV 兜底；
既命中 CDN 缓存、又未执行 JS 的访问无法统计。

### 7.5 启用配置

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/rewrz.conf /etc/nginx/sites-enabled/rewrz.conf
sudo nginx -t
sudo systemctl reload nginx
```

`default` 默认站点会抢占 `80` 端口，建议删除。

## 8. 配置 HTTPS

```bash
sudo certbot --nginx -d example.com
```

证书生效后无需修改 `.env`：Cookie 的 `Secure` 标志按请求自动判定，
HTTPS 下自动带上，HTTP 下自动不带。

## 9. 上线后验收清单

最少确认以下项目：

```bash
# 服务与配置
sudo systemctl status rewrz --no-pager
sudo nginx -t

# 首页与后台
curl -I https://example.com/
curl -I https://example.com/<你的ADMIN_PATH>/login

# 静态资源（必须 200，不能是跨域绝对地址）
curl -I https://example.com/static/css/site-tailwind.css
```

人工验收建议：
- 首页可打开
- 后台登录页可打开
- 静态资源不报 404
- 媒体上传目录可写
- 后台可正常登录
- 备份导出可执行

## 10. 宝塔面板（可选）

如果你使用宝塔，原则不变：
- 首次安装前不要先手工创建 `.env`
- 先把 Python 项目跑起来，再访问 `/installer`
- 安装完成后再编辑 `.env` 补生产配置
- 仍然执行一次 `alembic upgrade head`

最少确认：
- Python 项目启动命令正确
- Nginx 反代到正确端口
- 已开启 SSL
- `client_max_body_size 100m;` 已生效

## 11. 长期运维建议

- 日常更新优先使用仓库根目录的一键脚本，流程与参数见 [`UPDATE.md`](UPDATE.md)
- SQLite 生产环境保持单实例
- 定期导出备份，并做恢复演练
- 监控登录失败与异常请求
- 每次升级后都做首页、后台登录页、上传链路的最小烟测
