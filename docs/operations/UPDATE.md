# RewrZ 生产更新手册

本文档描述已上线站点的日常更新、回滚与最小验证流程。

如果你准备通过 GitHub Release ZIP 更新线上站点，先看：

- [`RELEASE.md`](RELEASE.md)

## 一键更新脚本（推荐）

仓库根目录提供了 `update.sh`，它按顺序完成备份、拉代码、装依赖、
执行数据库迁移、重启服务、重载 Nginx 与最小烟测，等价于本文「标准更新流程」。

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
- `REWRZ_HEALTH_TIMEOUT`：健康检查最长等待秒数，默认 `60`（应用冷启动约 30 秒）
- `REWRZ_BACKUP_KEEP`：备份保留份数，默认 `10`，设为 `0` 表示不自动清理

生产依赖保持在 `requirements.txt`；`pytest`、`httpx2` 等测试依赖已移入
`requirements-dev.txt`，本地跑测试时执行 `pip install -r requirements-dev.txt`。

说明：
- 备份写入 `backups/<时间戳>/`，脚本不会改写 `.env`
- 自 v3.1 起最低运行环境为 Python 3.12；`update.sh` 会在安装依赖前校验解释器版本，
  低于 3.12 直接报错退出，避免在旧解释器上装出半更新状态
- 备份成功后按 `REWRZ_BACKUP_KEEP` 只保留最近 N 份（默认 10，`0` 表示不清理）；
  清理只匹配脚本自身创建的 `backups/YYYY-MM-DD-HHMMSS/` 目录，
  `backups/` 下由 `pg_dump` 等手工生成的文件不会被删除，最新一份始终保留
- 数据库优先使用 `sqlite3 .backup` 在线备份并执行 `PRAGMA integrity_check`；
  无 `sqlite3` 时会先停服务再复制主库与 WAL/SHM
- 脚本会检测 `.env` 中重复的配置项并提示，但不会自动修复
- 重启后会等待 systemd 服务进入 active，再对健康检查入口做重试探测；
  应用冷启动约 30 秒，默认最多等待 60 秒，避免把启动过程误报为健康检查失败
- 重启前会检测 systemd 的 `--workers` 数量：本机内存 ≤1.5GB 且 worker 数大于 1 时，
  仅提示改为 `--workers 1`，不会自动改写服务配置
- 检测同时读取主 unit 与 `/etc/systemd/system/<服务名>.d/*.conf`，以 override 中的
  最后一项为准，避免已通过 drop-in 修正的配置被误报
- 同时检测 `--limit-concurrency`：缺失时仅提示设为 `20`，与默认连接池 16+8 配合，
  避免并发把连接池打满，同样不会自动改写服务配置
- 小内存机器还会检测 `MALLOC_ARENA_MAX`：未设置时提示加入 `Environment=MALLOC_ARENA_MAX=2`，
  避免 glibc 线程内存池长期占用 RSS
- 数据库表结构由应用启动时的 `create_all` 自动维护（只建不存在的表）；
  `alembic/versions/` 下的迁移脚本只承载 `create_all` 无法覆盖的数据变更
- `update.sh` 会在依赖安装后执行 `alembic upgrade head`（未检测到 `.env` 时跳过，
  新站点由安装向导建表并标记版本）；若检测到已废弃的历史
  revision，会先 `alembic stamp --purge base` 重置基线再迁移，不会重复建表
- 手工执行流程见下文，二者保持一致；修改脚本时必须同步本文

## 1. 更新原则

- 先备份，再更新
- 先停服务，再改代码
- 表结构由应用启动时的 `create_all` 自动补齐；数据迁移由 `update.sh` 执行
  `alembic upgrade head`
- 历史迁移脚本已全部废弃删除；生产库若残留旧 revision，脚本会自动重置迁移基线

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

如果你已启用 PostgreSQL，`update.sh` 的自动备份只会提示“未定位到数据库文件”
并跳过数据库部分。更新前必须手工执行原生备份：

```bash
cd /srv/rewrz
mkdir -p backups
pg_dump --format=custom \
  --file="backups/rewrz-$(date +%F-%H%M%S).dump" \
  -d "postgresql://rewrz:密码@127.0.0.1:5432/rewrz"
```

建议把密码写入权限为 `600` 的 `~/.pgpass`，避免出现在 shell 历史与进程列表。
执行 `./update.sh` 时仍应保留自动备份（它还会备份 `.env` 与媒体目录），
不要因为数据库备份已手工完成就加 `--no-backup`。

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

`requirements.txt` 中的 `tzdata` 提供 IANA 时区数据库，缺少时
`SITE_TIMEZONE` 会回落到默认时区，`update.sh` 会在依赖检查阶段直接报错。

### 3.4 数据库迁移（自动）

表结构仍由应用启动时的 `create_all` 自动补齐；`alembic/versions/` 中的脚本用于
`create_all` 无法覆盖的数据变更。使用 `update.sh` 时会自动执行迁移；手工更新时
执行：

```bash
cd /srv/rewrz
source .venv/bin/activate
alembic current
alembic upgrade head
```

若 `alembic current` 报 `Can't locate revision`（旧迁移脚本已废弃删除），先重置
迁移基线再执行：

```bash
alembic stamp --purge base
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

应用冷启动约需 30 秒，服务刚恢复时探测失败属于正常现象，应重试而非立即判定失败。

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
    `SQLITE_BUSY_TIMEOUT_MS`、`SQLITE_JOURNAL_MODE`、`SQLITE_CACHE_SIZE_KIB`、
    `SQLITE_SYNCHRONOUS` 均可选，不写时使用默认值；
    诊断阈值 `SLOW_SQL_LOG_MS`、`DB_HOLD_WARN_MS` 同样可选；
    `update.sh` 只检测 `.env`，不会自动写入这些配置
  - SQLite 站点的 systemd `ExecStart` 需要带 `--limit-concurrency 20`，
    与默认连接池 16+8 配合，避免并发把池打满
- PostgreSQL 站点重建虚拟环境后：
  - `requirements.txt` 不包含 PostgreSQL 驱动，需要重新执行
    `pip install "psycopg[binary]"`
  - 否则应用启动时会因缺少驱动无法连接数据库

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
