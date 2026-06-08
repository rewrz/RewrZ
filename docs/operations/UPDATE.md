# RewrZ 生产更新手册

本文档描述已上线站点的日常更新、回滚与最小验证流程。

## 1. 更新原则

- 先备份，再更新
- 先停服务，再改代码和数据库
- 先执行迁移，再恢复服务
- Alembic 一旦改动生产库，不要指望临时 `downgrade` 解决问题；回滚优先恢复备份

## 2. 更新前备份

至少备份以下三类内容：

```bash
cd /srv/rewrz

cp .env .env.backup.$(date +%F-%H%M%S)
cp data/rewrz.db data/rewrz.db.backup.$(date +%F-%H%M%S)
tar -czf media_uploads.backup.$(date +%F-%H%M%S).tar.gz media_uploads
```

如果你已启用 PostgreSQL，请改为数据库原生备份命令。

更新前建议额外记录：
- 当前代码提交号
- 当前 `ADMIN_PATH`
- 当前服务状态

## 3. 标准更新流程

### 3.1 停止服务

```bash
sudo systemctl stop rewrz
```

### 3.2 更新代码

推荐切到明确版本，而不是盲目长期 `git pull`：

```bash
cd /srv/rewrz
git fetch --all --tags
git checkout <目标提交或标签>
```

### 3.3 更新 Python 依赖

```bash
cd /srv/rewrz
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.4 执行数据库迁移

```bash
cd /srv/rewrz
source .venv/bin/activate
alembic upgrade head
```

### 3.5 恢复服务

```bash
sudo systemctl start rewrz
sudo systemctl status rewrz --no-pager
```

如 Nginx 也有配置变更，再执行：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 4. 更新后最小烟测

至少检查以下项目：

```bash
curl -I https://example.com/
curl -I https://example.com/<你的ADMIN_PATH>/login
sudo journalctl -u rewrz -n 100 --no-pager
```

人工验收建议：
- 首页正常打开
- 后台登录页正常打开
- 登录后仪表盘正常进入
- 新建/编辑内容页无明显报错
- 媒体上传可用
- 备份导出可用

## 5. 什么时候需要额外动作

以下场景建议额外处理：

- 依赖大版本升级：
  - 先在测试环境完整验证
- 涉及模板/Tailwind 改动，但仓库未提交最新 CSS：
  - 执行 `npm install`
  - 执行 `npm run build:css`
- 反向代理或证书有改动：
  - 重新检查 Nginx 与 HTTPS 配置
- `.env` 新增配置项：
  - 按变更说明补齐
  - 再重启服务

## 6. 回滚流程

如果更新后出现阻塞问题，按以下顺序回滚：

### 6.1 停止服务

```bash
sudo systemctl stop rewrz
```

### 6.2 恢复旧代码

```bash
cd /srv/rewrz
git checkout <上一个稳定提交或标签>
source .venv/bin/activate
pip install -r requirements.txt
```

### 6.3 恢复配置、数据库、媒体

```bash
cp .env.backup.<时间戳> .env
cp data/rewrz.db.backup.<时间戳> data/rewrz.db
rm -rf media_uploads
tar -xzf media_uploads.backup.<时间戳>.tar.gz
```

### 6.4 启动旧版本

```bash
sudo systemctl start rewrz
sudo systemctl status rewrz --no-pager
```

说明：
- 如果本次更新已经执行了生产迁移，优先恢复整个数据库备份
- 不建议把生产回滚建立在 `alembic downgrade` 的临时运气上

## 7. 常见失误

- 更新前没备份数据库和媒体目录
- 用多个实例同时指向同一个 SQLite
- 更新了代码但没执行 `alembic upgrade head`
- HTTPS 已启用但 `.env` 还保持 `COOKIE_SECURE=false`
- 修改了 `.env` 却忘了重启服务
