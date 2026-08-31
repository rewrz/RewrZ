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

编辑 `/srv/rewrz/.env`，至少确认以下项：

```env
COOKIE_SECURE=true
SESSION_HTTPS_ONLY=true
```

不要使用 `echo >> .env` 直接追加，重复键会导致配置歧义（后写的值覆盖前面的）。
请先把整行删除再写入，保证每个键只出现一次、可重复执行：

```bash
sed -i '/^COOKIE_SECURE=/d;/^SESSION_HTTPS_ONLY=/d' .env
cat >> .env <<'EOF'
COOKIE_SECURE=true
SESSION_HTTPS_ONLY=true
EOF
```

注意：`COOKIE_SECURE=true` 只在 HTTPS 生效后才启用。
如果你仍在 HTTP 下访问，保持 `false`，否则会出现登录后立即掉线。

如需邮件能力，再补：

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-user
SMTP_PASSWORD=your-password
SMTP_FROM=notify@example.com
```

建议同时核对：
- `ADMIN_PATH` 是否为安装向导生成的隐藏后台路径
- `DATABASE_URL` 是否指向你真正要使用的生产库
- `MEDIA_UPLOAD_DIR` 是否与实际媒体目录一致

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
ExecStart=/srv/rewrz/.venv/bin/uvicorn rewrz.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

然后执行：

```bash
sudo chown -R www-data:www-data /srv/rewrz
sudo systemctl daemon-reload
sudo systemctl enable rewrz
sudo systemctl start rewrz
sudo systemctl status rewrz
```

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
```

说明：
- `alias` 路径中的 `/srv/rewrz` 要替换成你的实际部署目录
- 文中出现的 `$http_host` 是 Nginx 变量，不是 shell 变量，不要转义

### 7.3 启用配置

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

证书生效后，再检查一次 `.env`：
- `COOKIE_SECURE=true`
- `SESSION_HTTPS_ONLY=true`

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
