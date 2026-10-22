# RewrZ 生产更新手册

本文档描述已上线站点的日常更新、回滚与最小验证流程。

如果你准备通过 GitHub Release ZIP 更新线上站点，先看：

- [`RELEASE.md`](RELEASE.md)

## 一键更新脚本（推荐）

仓库根目录提供了 `update.sh`，它按顺序完成备份、拉代码、装依赖、
重启服务、重载 Nginx 与最小烟测，等价于本文「标准更新流程」。

```bash
cd /srv/rewrz                      # 换成你的部署目录
chmod +x update.sh
./update.sh                        # 更新到当前分支最新
./update.sh v0.9.2                 # 更新到指定标签或提交
./update.sh --no-backup            # 已有备份时跳过自动备份
```

可用环境变量：
- `REWRZ_SERVICE`：systemd 服务名，默认 `rewrz.service`
- `REWRZ_HEALTH_URL`：健康检查入口，默认 `http://127.0.0.1:8000/`

生产依赖保持在 `requirements.txt`；`pytest`、`httpx2` 等测试依赖已移入
`requirements-dev.txt`，本地跑测试时执行 `pip install -r requirements-dev.txt`。

说明：
- 备份写入 `backups/<时间戳>/`，脚本不会改写 `.env`
- 数据库优先使用 `sqlite3 .backup` 在线备份并执行 `PRAGMA integrity_check`；
  无 `sqlite3` 时会先停服务再复制主库与 WAL/SHM
- 脚本会检测 `.env` 中重复的配置项并提示，但不会自动修复
- 数据库表结构由应用启动时的 `create_all` 自动维护（只建不存在的表），
  不需要也不应当执行 `alembic upgrade head`
- 手工执行流程见下文，二者保持一致；修改脚本时必须同步本文

## 1. 更新原则

- 先备份，再更新
- 先停服务，再改代码
- 表结构随应用启动自动补齐，无需单独执行数据库迁移
- Alembic 迁移脚本仅服务于本地开发库的 schema 演进；不要在生产库上执行
  `alembic upgrade head`（生产库缺少迁移脚本，必然失败），回滚优先恢复备份

## 2. 更新前备份

至少备份以下三类内容：

```bash
cd /srv/rewrz

STAMP=$(date +%F-%H%M%S)
cp .env ".env.backup.$STAMP"
chmod 600 ".env.backup.$STAMP"

# SQLite：优先使用在线备份获取一致快照，并做完整性校验
sqlite3 data/rewrz.db ".backup 'data/rewrz.db.backup.$STAMP'"
sqlite3 "data/rewrz.db.backup.$STAMP" "PRAGMA integrity_check;"

tar -czf "media_uploads.backup.$STAMP.tar.gz" media_uploads
```

没有 `sqlite3` 命令时，必须先停止服务，再复制 `data/rewrz.db`、
`data/rewrz.db-wal`、`data/rewrz.db-shm` 三个文件；只复制主库文件会丢失
WAL 中尚未合并的事务。

如果你已启用 PostgreSQL，请改为数据库原生备份命令。
备份目录与 `.env` 副本应保持私有权限（目录 `700`、文件 `600`），
避免同机其他用户读取数据库或密钥。

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

推荐切到明确版本，而不是盲目长期 `git pull`。如果你使用本地生成的 GitHub Release 发布包，也应先确认包名和版本号与目标版本一致：

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

### 3.4 数据库表结构（自动）

不需要手工执行迁移。应用启动时会调用 `create_all` 基于当前模型补齐缺失的表
和列（已存在的对象不动），因此更新代码后直接恢复服务即可：

```bash
sudo systemctl start rewrz
sudo journalctl -u rewrz -n 50 --no-pager   # 确认无启动报错
```

如对表结构变更有疑问，可对照本地开发库的 `alembic/versions/` 迁移脚本。

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
  - 数据库池参数 `DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_POOL_TIMEOUT`、
    `DB_POOL_RECYCLE`、`DB_POOL_PRE_PING` 与 SQLite 参数
    `SQLITE_BUSY_TIMEOUT_MS`、`SQLITE_JOURNAL_MODE` 均可选，不写时使用默认值；
    `update.sh` 只检测 `.env`，不会自动写入这些配置

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
- 如需回滚数据库变更，优先恢复整个数据库备份
- 不建议把生产回滚建立在 `alembic downgrade` 的临时运气上

## 7. 常见失误

- 更新前没备份数据库和媒体目录
- 用多个实例同时指向同一个 SQLite
- 更新了代码但没重启服务（表结构与新代码要等重启后才生效）
- 修改了 `.env` 却忘了重启服务
