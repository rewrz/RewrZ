# RewrZ 使用文档

本文档面向站长与运营者，包含本地运行、线上部署、日常运维三部分。

## 1. 环境要求
- Python 3.10+
- 建议 512MB 以上内存
- Linux/Windows/macOS 均可运行（生产推荐 Linux）

## 2. 本地运行（开发/测试）

### 2.1 启动步骤
```bash
git clone https://github.com/rewrz/RewrZ.git
cd RewrZ
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn rewrz.main:app --reload
```

启动后访问：`http://127.0.0.1:8000/installer`

### 2.2 安装向导流程
1. 环境检查
2. 数据库初始化
3. 管理员创建
4. 站点配置
5. 后台路径配置
6. 完成安装并进入登录页

安装完成后会生成 `.env`（包含 `SECRET_KEY`、`DATABASE_URL`、`ADMIN_PATH` 等）。

## 3. 线上部署（推荐：systemd + Nginx + HTTPS）

以下示例以 Ubuntu 为例，域名使用 `example.com`，项目路径使用 `/srv/rewrz`。

### 3.1 准备服务器
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git
```

### 3.2 拉取代码并安装依赖
```bash
sudo mkdir -p /srv
cd /srv
sudo git clone https://github.com/rewrz/RewrZ.git rewrz
sudo chown -R $USER:$USER /srv/rewrz
cd /srv/rewrz

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.3 配置生产环境变量
创建 `/srv/rewrz/.env`，示例：
```env
DATABASE_URL=sqlite:///./data/rewrz.db
SECRET_KEY=请替换为高强度随机字符串
ADMIN_PATH=/your-hidden-admin-path
MEDIA_UPLOAD_DIR=media_uploads
COOKIE_SECURE=true
SESSION_HTTPS_ONLY=true
```

首次部署先启动一次应用并完成 `/installer` 安装流程：
```bash
source /srv/rewrz/.venv/bin/activate
uvicorn rewrz.main:app --host 0.0.0.0 --port 8000
```

### 3.4 配置 systemd（常驻运行）
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

执行：
```bash
sudo chown -R www-data:www-data /srv/rewrz
sudo systemctl daemon-reload
sudo systemctl enable rewrz
sudo systemctl start rewrz
sudo systemctl status rewrz
```

### 3.5 配置 Nginx 反向代理
创建 `/etc/nginx/sites-available/rewrz.conf`：
```nginx
server {
    listen 80;
    server_name example.com;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/rewrz.conf /etc/nginx/sites-enabled/rewrz.conf
sudo nginx -t
sudo systemctl reload nginx
```

### 3.6 配置 HTTPS（Let’s Encrypt）
```bash
sudo certbot --nginx -d example.com
```

成功后建议再次确认：
- `.env` 中 `COOKIE_SECURE=true`
- `.env` 中 `SESSION_HTTPS_ONLY=true`

### 3.7 宝塔面板部署（可选）
如果你使用宝塔面板，可以按下面流程部署（适合不想手工维护 `systemd` 的场景）。

1. 准备运行环境  
在宝塔安装：
- Python 项目管理器
- Nginx
- Git

2. 拉取项目  
在服务器目录（例如 `/www/wwwroot`）执行：
```bash
cd /www/wwwroot
git clone https://github.com/rewrz/RewrZ.git rewrz
cd rewrz
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. 在宝塔创建 Python 项目  
宝塔面板 -> Python 项目 -> 添加项目：
- 项目路径：`/www/wwwroot/rewrz`
- 启动方式：`uvicorn`
- 启动命令：`.venv/bin/uvicorn rewrz.main:app --host 127.0.0.1 --port 8000 --workers 2`
- 绑定域名：你的域名（例如 `example.com`）

4. 配置环境变量  
在项目目录创建 `.env`：
```env
DATABASE_URL=sqlite:///./data/rewrz.db
SECRET_KEY=请替换为高强度随机字符串
ADMIN_PATH=/your-hidden-admin-path
MEDIA_UPLOAD_DIR=media_uploads
COOKIE_SECURE=true
SESSION_HTTPS_ONLY=true
```

5. 首次初始化  
先访问 `http://你的域名/installer` 完成安装向导。  
完成后重启 Python 项目。

6. 开启 SSL  
在宝塔网站设置中申请 Let’s Encrypt 证书并开启强制 HTTPS。

7. 上传大小限制  
在宝塔网站的 Nginx 配置中补充：
```nginx
client_max_body_size 100m;
```
保存后重载 Nginx，避免媒体上传或备份导入被网关层拒绝。

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

## 5. 日常使用

### 5.1 内容发布
- `post_type` 仅支持：`post`（文章）与 `page`（页面）。
- `article/micro/poem` 通过内容意图（formats）管理，不是主类型。

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
安装完成后 installer 默认关闭，这是正常行为。

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

### Q8：出现 `database is locked`（SQLite 锁库）怎么办？
1. 先确认没有多个重复实例在同时写同一个 SQLite 文件
2. 减少并发写入压力（尤其导入/批量操作时）
3. 保持数据库文件在本地磁盘，不要放在高延迟网络存储
4. 若长期高并发写入，建议迁移到 PostgreSQL

## 9. 文档入口
- 文档中心：[`docs/INDEX.md`](../INDEX.md)
- 项目总览：[`README.md`](../../README.md)
- 开发文档：[`DEVELOPMENT.md`](DEVELOPMENT.md)
