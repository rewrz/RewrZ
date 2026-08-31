# RewrZ 故障排查手册

本文档只保留当前仍然成立的故障定位方式。

## 1. 服务无法启动

### 1.1 症状
- 访问站点报 `502` 或连接失败
- `uvicorn` 启动后立即退出

### 1.2 排查步骤
```bash
# systemd 模式
sudo systemctl status rewrz
sudo journalctl -u rewrz -n 200 --no-pager

# 直接运行模式
source .venv/bin/activate
uvicorn rewrz.main:app --host 127.0.0.1 --port 8000
```

优先检查：
1. `.env` 是否存在且格式正确
2. 虚拟环境依赖是否完整
3. 运行用户是否有项目目录读写权限

## 2. 安装流程异常

### 2.1 访问 `/installer` 被跳转到 `/`
原因：系统已判定为安装完成（有效 `.env` + `DATABASE_URL` 已生效）。

处理：
1. 确认是否确实需要重装
2. 重装前先备份数据库与 `media_uploads/`
3. 再处理 `.env` 与数据目录

### 2.2 安装最后一步失败后想继续安装
当前版本会自动回滚本次失败生成的 `.env`。

如果你仍然无法继续：
1. 先确认运行的确实是最新代码
2. 检查项目根目录是否残留错误 `.env`
3. 确认 `REWRZ_ENV_FILE` 没有指向错误位置
4. 重新访问 `/installer`

### 2.3 初始内容显示「创建了 0 个分类」
初始内容按「实际新增」计数，以下情况计数为 0 属正常：
- 未勾选对应选项
- 分类/标签/内容类型已存在（重复提交不会重复创建）

如果页面直接报「创建失败」，先看应用日志中的具体错误，再检查数据库是否可写。

## 3. 登录与鉴权问题

### 3.1 登录后立即掉线
常见原因是 Cookie 安全策略与协议不一致：
- HTTP 场景不应启用 `COOKIE_SECURE=true`
- HTTPS 场景建议同时启用：
  - `COOKIE_SECURE=true`
  - `SESSION_HTTPS_ONLY=true`

### 3.2 后台写接口返回 403
重点检查 CSRF：
- 请求是否携带 `X-CSRF-Token`
- 会话中 token 与提交 token 是否一致

### 3.3 忘记密码链路无法完成

优先区分两类问题：

1. 产品链路问题
- `/rewrz-admin/forgot-password` 是否可访问
- 重置链接是否可生成
- 重置成功后是否跳回登录页

2. 环境问题
- 是否已重启到最新服务代码
- 数据库是否已执行最新 Alembic 迁移
- 是否已配置 SMTP；若未配置，检查：
  - `data/logs/password_reset_debug.log`

## 4. 上传与导入问题

### 4.1 上传大文件失败
检查两层限制：
1. 应用层媒体大小限制（后台配置）
2. 反向代理限制（如 Nginx `client_max_body_size`）

### 4.2 备份导入失败
RewrZ 会拒绝不安全备份包，包括：
- 路径越界（Zip Slip）
- 压缩比异常
- 文件数量/体积超限

如果是可信备份仍失败，先检查备份包结构与日志输出。

## 5. SQLite 锁库问题

### 5.1 报错
- `database is locked`

### 5.2 建议
1. 避免多个实例同时写同一个 SQLite 文件
2. 高并发写场景减少批量写峰值
3. 数据文件放本地磁盘，不放高延迟网络盘
4. 长期高并发建议迁移 PostgreSQL

## 6. 数据库迁移

### 6.1 全新安装后执行 `alembic upgrade head` 报 duplicate table
原因：安装向导建库时已经完成建表，并把新库标记为 Alembic head；
新装站点再执行 `upgrade head` 会重复建表。

处理：
1. `alembic current` 确认版本是否已是 head
2. 新装站点无需执行迁移，只有更新已有站点才需要

### 6.2 迁移目标库不是预期数据库
迁移目标库优先读取 `.env` 的 `DATABASE_URL`，`alembic.ini` 只是兜底值：
1. 确认命令在项目根目录执行
2. 确认 `.env` 中的 `DATABASE_URL` 指向目标库

## 7. 宝塔常见问题

### 6.1 502 Bad Gateway
1. 宝塔 Python 项目是否在运行
2. 启动命令、端口与 Nginx 反代是否一致
3. 查看宝塔项目日志与 Nginx 错误日志

### 6.2 静态资源 404
1. 项目路径是否正确（包含 `rewrz/static`）
2. `MEDIA_UPLOAD_DIR` 是否指向真实目录
3. 权限是否允许运行用户读取

### 6.3 本地修改已保存，但页面行为还是旧的
优先检查：
1. 当前监听端口上的进程是否就是当前仓库 `.venv` 启动的实例
2. 是否存在旧的 `uvicorn` 进程占用了同一端口
3. 修改后是否已经重启服务

## 8. 快速自检清单

```bash
# 1) 应用进程
ps -ef | grep uvicorn

# 2) 端口监听
ss -lntp | grep 8000

# 3) Nginx 配置语法
sudo nginx -t

# 4) Python 依赖
source .venv/bin/activate && pip check

# 5) Alembic 迁移
alembic current
alembic upgrade head
```
