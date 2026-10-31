#!/bin/bash
# RewrZ 一键更新部署脚本
#
# 用法:
#   ./update.sh                 更新到当前分支最新
#   ./update.sh v0.9.2          更新到指定标签或提交
#   ./update.sh --no-backup     跳过更新前自动备份
#   REWRZ_BACKUP_KEEP=5 ./update.sh  备份只保留最近 5 份（默认 10，0 表示不清理）
#
# 维护约定:
#   本脚本是生产更新手册 docs/operations/UPDATE.md 的可执行版本。
#   依赖、数据库迁移、静态资源构建、服务管理方式发生变化时,
#   必须同时修改本脚本、UPDATE.md 与 AGENTS.md 中的维护约定。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SERVICE_NAME="${REWRZ_SERVICE:-rewrz.service}"
HEALTH_URL="${REWRZ_HEALTH_URL:-http://127.0.0.1:8000/}"
HEALTH_TIMEOUT="${REWRZ_HEALTH_TIMEOUT:-60}"
TARGET_REF=""
DO_BACKUP=true
BACKUP_KEEP="${REWRZ_BACKUP_KEEP:-10}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "$1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

# 清理过期备份：只处理脚本自身创建的 backups/<YYYY-MM-DD-HHMMSS>/ 目录，
# backups/ 下由 pg_dump 等手工生成的文件不会被删除；最新一份始终保留。
prune_old_backups() {
    local keep="$1" dir removed=0 i
    local -a dirs=() sorted=()

    for dir in "$SCRIPT_DIR"/backups/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]; do
        [ -d "$dir" ] || continue
        dirs+=("$dir")
    done

    if [ "${#dirs[@]}" -le "$keep" ]; then
        ok "备份保留策略: 现有 ${#dirs[@]} 份，未超过上限 ${keep} 份"
        return 0
    fi

    # 目录名即时间戳，按名称升序排序后清理最早的部分
    while IFS= read -r dir; do
        sorted+=("$dir")
    done < <(printf '%s\n' "${dirs[@]}" | sort)

    for ((i = 0; i < ${#dirs[@]} - keep; i++)); do
        if ! rm -rf -- "${sorted[$i]}"; then
            warn "清理旧备份失败: $(basename "${sorted[$i]}")，请手工检查 backups/ 权限"
            return 1
        fi
        info "已清理旧备份: $(basename "${sorted[$i]}")"
        removed=$((removed + 1))
    done

    ok "备份保留策略: 保留最近 ${keep} 份，本次清理 ${removed} 份"
}

if ! [[ "$HEALTH_TIMEOUT" =~ ^[0-9]+$ ]] || [ "$HEALTH_TIMEOUT" -le 0 ]; then
    fail "REWRZ_HEALTH_TIMEOUT 必须是正整数秒（当前: $HEALTH_TIMEOUT）"
fi

if ! [[ "$BACKUP_KEEP" =~ ^[0-9]+$ ]]; then
    fail "REWRZ_BACKUP_KEEP 必须是非负整数（当前: $BACKUP_KEEP）"
fi

for arg in "$@"; do
    case "$arg" in
        --no-backup)
            DO_BACKUP=false
            ;;
        -h|--help)
            sed -n '2,13p' "$0"
            exit 0
            ;;
        *)
            TARGET_REF="$arg"
            ;;
    esac
done

echo "=========================================="
echo "  RewrZ 一键更新部署脚本"
echo "=========================================="
echo ""

# 1. 检查是否在项目目录
if [ ! -f "rewrz/main.py" ]; then
    fail "当前目录不是 RewrZ 项目目录: $SCRIPT_DIR"
fi

# 2. 检查虚拟环境
if [ ! -x ".venv/bin/python" ]; then
    fail "未找到虚拟环境 .venv，请先按 docs/operations/DEPLOYMENT.md 完成首次部署"
fi

# 3. 记录更新前状态
if git rev-parse --git-dir >/dev/null 2>&1; then
    IN_GIT_REPO=true
    OLD_REV="$(git rev-parse HEAD)"
    info "当前版本: $(git rev-parse --short HEAD)"
else
    IN_GIT_REPO=false
    OLD_REV=""
    warn "非 git 仓库，跳过代码更新与变更检测"
fi

# 4. 更新前备份
if [ "$DO_BACKUP" = true ]; then
    echo ""
    echo ">>> 更新前备份..."
    BACKUP_DIR="$SCRIPT_DIR/backups/$(date +%F-%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    chmod 700 "$BACKUP_DIR"

    if [ -f ".env" ]; then
        cp .env "$BACKUP_DIR/.env"
        chmod 600 "$BACKUP_DIR/.env"
    else
        warn ".env 不存在，跳过配置备份"
    fi

    if [ -f ".env" ]; then
        DB_PATH="$(grep -E '^DATABASE_URL=' .env | head -1 \
            | sed -E 's/^DATABASE_URL=//; s/^"//; s/"$//; s|^sqlite[+]?[a-z]*:///||' || true)"
    else
        DB_PATH=""
    fi

    if [ -n "$DB_PATH" ] && [ -f "$DB_PATH" ]; then
        DB_BASENAME="$(basename "$DB_PATH")"
        if command -v sqlite3 >/dev/null 2>&1; then
            # 在线备份可获取一致快照，无需手工复制 -wal/-shm
            sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/$DB_BASENAME'"
            INTEGRITY_RESULT="$(sqlite3 "$BACKUP_DIR/$DB_BASENAME" 'PRAGMA integrity_check;' || true)"
            if [ "$INTEGRITY_RESULT" = "ok" ]; then
                ok "数据库已在线备份并通过完整性校验: $DB_PATH"
            else
                fail "数据库备份完整性校验失败: $INTEGRITY_RESULT"
            fi
        else
            # 无 sqlite3 时先停服务再复制主库与 WAL/SHM，避免备份处于不一致状态
            if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
                sudo systemctl stop "$SERVICE_NAME"
                warn "为保证备份一致性已临时停止 $SERVICE_NAME（后续步骤会重新启动）"
            fi
            cp "$DB_PATH" "$BACKUP_DIR/$DB_BASENAME"
            if [ -f "${DB_PATH}-wal" ]; then
                cp "${DB_PATH}-wal" "$BACKUP_DIR/${DB_BASENAME}-wal"
            fi
            if [ -f "${DB_PATH}-shm" ]; then
                cp "${DB_PATH}-shm" "$BACKUP_DIR/${DB_BASENAME}-shm"
            fi
            ok "数据库已备份（含 WAL/SHM）: $DB_PATH"
        fi
    else
        warn "未定位到数据库文件（DATABASE_URL=$DB_PATH），跳过数据库备份"
    fi

    MEDIA_DIR="$(grep -E '^MEDIA_UPLOAD_DIR=' .env 2>/dev/null | head -1 \
        | sed -E 's/^MEDIA_UPLOAD_DIR=//; s/^"//; s/"$//' || true)"
    MEDIA_DIR="${MEDIA_DIR:-media_uploads}"
    if [ -d "$MEDIA_DIR" ]; then
        tar -czf "$BACKUP_DIR/media_uploads.tar.gz" "$MEDIA_DIR"
        ok "媒体目录已备份: $MEDIA_DIR"
    fi

    ok "备份目录: $BACKUP_DIR"

    echo ""
    if [ "$BACKUP_KEEP" -gt 0 ]; then
        echo ">>> 清理过期备份（保留最近 ${BACKUP_KEEP} 份）..."
        prune_old_backups "$BACKUP_KEEP" || warn "旧备份清理未完成，本次更新继续"
    else
        info "备份保留策略: REWRZ_BACKUP_KEEP=0，跳过旧备份清理"
    fi
else
    warn "已按参数跳过备份（--no-backup）"
fi

# 5. 更新代码
CHANGED=false
if [ "$IN_GIT_REPO" = true ]; then
    echo ""
    echo ">>> 更新代码..."
    git fetch --all --tags

    if [ -n "$TARGET_REF" ]; then
        git checkout "$TARGET_REF"
        ok "已切换到: $TARGET_REF"
        CHANGED=true
    elif git symbolic-ref -q HEAD >/dev/null 2>&1; then
        LOCAL_REV="$(git rev-parse HEAD)"
        REMOTE_REV="$(git rev-parse '@{u}')"
        if [ "$LOCAL_REV" = "$REMOTE_REV" ]; then
            ok "代码已是最新"
        else
            git pull --rebase
            ok "代码已更新"
            CHANGED=true
        fi
    else
        warn "当前处于分离 HEAD，未自动拉取；如需切换版本请执行: ./update.sh <标签或提交>"
    fi
fi

# 6. 安装/更新依赖
echo ""
echo ">>> 检查 Python 依赖..."
PY_VERSION="$(.venv/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo unknown)"
if ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
    fail "Python 版本过低（当前 ${PY_VERSION}），RewrZ 最低需要 Python 3.12"
fi
.venv/bin/pip install -q -r requirements.txt
if ! .venv/bin/python -c "import bcrypt" >/dev/null 2>&1; then
    fail "bcrypt 依赖不可用，请检查 requirements.txt 安装结果"
fi
if ! .venv/bin/python -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Shanghai')" >/dev/null 2>&1; then
    fail "tzdata 依赖不可用，时区转换需要它，请检查 requirements.txt 安装结果"
fi
ok "依赖已就绪"

# 7. 检查 .env 是否存在重复配置项
if [ -f ".env" ]; then
    DUPLICATE_KEYS="$(grep -vE '^[[:space:]]*(#|$)' .env | cut -d= -f1 | sort | uniq -d || true)"
    if [ -n "$DUPLICATE_KEYS" ]; then
        warn ".env 存在重复配置项（后面的值会覆盖前面的），请手工去重："
        echo "$DUPLICATE_KEYS" | sed 's/^/       - /'
    else
        ok ".env 无重复配置项"
    fi
else
    warn ".env 不存在，请先运行安装向导 /installer"
fi

# 7.1 数据库迁移（仅对已安装站点执行，新站点由安装向导建表并标记版本）
echo ""
echo ">>> 执行数据库迁移..."
if [ ! -f ".env" ]; then
    warn "未检测到 .env，跳过数据库迁移；新站点请先完成安装向导 /installer"
elif [ -f "alembic.ini" ]; then
    # 旧迁移脚本已废弃删除；若数据库仍记录旧 revision，先重置到空基线再迁移。
    if ! ALEMBIC_STATE="$(.venv/bin/python -m alembic current 2>&1)"; then
        if printf '%s' "$ALEMBIC_STATE" | grep -q "Can't locate revision"; then
            warn "检测到已废弃的历史迁移版本，正在重置迁移基线..."
            .venv/bin/python -m alembic stamp --purge base || fail "重置数据库迁移基线失败"
        else
            fail "读取数据库迁移状态失败: ${ALEMBIC_STATE}"
        fi
    fi
    .venv/bin/python -m alembic upgrade head || fail "数据库迁移失败，请检查 DATABASE_URL 与迁移日志"
    ok "数据库迁移已应用到最新版本"
else
    warn "未找到 alembic.ini，跳过数据库迁移"
fi

# 8. 提示前端产物重建
if [ "$IN_GIT_REPO" = true ] && [ "$CHANGED" = true ] && [ -n "$OLD_REV" ]; then
    FRONTEND_CHANGED="$(git diff --name-only "$OLD_REV" HEAD -- rewrz/templates tailwind.config.js package.json 2>/dev/null || true)"
    if [ -n "$FRONTEND_CHANGED" ]; then
        warn "检测到模板或 Tailwind 配置变更："
        echo "$FRONTEND_CHANGED" | sed 's/^/       - /'
        warn "若仓库未提交最新 CSS 产物，请执行: npm install && npm run build:css"
    fi
fi

# 8.1 小内存部署提示（仅检测，不修改 systemd 配置）
SERVICE_UNIT="/etc/systemd/system/$SERVICE_NAME"
if [ -f "$SERVICE_UNIT" ]; then
    WORKER_COUNT="$(grep -oE -- '--workers[= ][0-9]+' "$SERVICE_UNIT" | head -n1 | grep -oE '[0-9]+' || true)"
    TOTAL_MEM_MB="$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)"
    if [ -n "${WORKER_COUNT:-}" ] && [ "$WORKER_COUNT" -gt 1 ] && [ "${TOTAL_MEM_MB:-0}" -gt 0 ] && [ "$TOTAL_MEM_MB" -le 1536 ]; then
        warn "检测到 systemd 使用 ${WORKER_COUNT} 个 worker，本机内存 ${TOTAL_MEM_MB}MB；建议改为 --workers 1 并设置 MALLOC_ARENA_MAX=2，避免整机 OOM"
    fi
    if ! grep -q -- '--limit-concurrency' "$SERVICE_UNIT"; then
        warn "systemd 未设置 --limit-concurrency；建议设为 20，与默认连接池 16+8 配合，避免并发把连接池打满"
    fi
fi

# 9. 重启服务
echo ""
echo ">>> 重启服务..."
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    sudo systemctl restart "$SERVICE_NAME"
    SERVICE_ACTIVE=false
    for _ in {1..10}; do
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            SERVICE_ACTIVE=true
            break
        fi
        sleep 1
    done
    if [ "$SERVICE_ACTIVE" = true ]; then
        ok "$SERVICE_NAME 已重启"
    else
        fail "$SERVICE_NAME 重启失败，请执行: sudo journalctl -u ${SERVICE_NAME%.service} -n 50"
    fi
elif systemctl cat "$SERVICE_NAME" >/dev/null 2>&1; then
    sudo systemctl start "$SERVICE_NAME"
    ok "$SERVICE_NAME 已启动"
else
    warn "未找到 $SERVICE_NAME，请按 docs/operations/DEPLOYMENT.md 配置 systemd 后手动启动"
fi

# 10. 重新加载 Nginx（仅在配置通过检测时）
if [ "$CHANGED" = true ] && command -v nginx >/dev/null 2>&1; then
    echo ""
    echo ">>> 检查 Nginx..."
    if sudo nginx -t 2>/dev/null; then
        sudo systemctl reload nginx
        ok "Nginx 已重新加载"
    else
        warn "Nginx 配置检测未通过或权限不足，跳过重载"
    fi
fi

# 11. 最小烟测（应用冷启动约 30 秒，需重试等待）
echo ""
echo ">>> 最小烟测（最长等待 ${HEALTH_TIMEOUT}s）..."
if command -v curl >/dev/null 2>&1; then
    HEALTH_OK=false
    HEALTH_DEADLINE=$((SECONDS + HEALTH_TIMEOUT))
    while [ "$SECONDS" -lt "$HEALTH_DEADLINE" ]; do
        if curl -fsS -o /dev/null --max-time 10 "$HEALTH_URL" >/dev/null 2>&1; then
            HEALTH_OK=true
            break
        fi
        sleep 2
    done
    if [ "$HEALTH_OK" = true ]; then
        ok "健康检查通过: $HEALTH_URL"
    else
        warn "健康检查在 ${HEALTH_TIMEOUT}s 内未通过: $HEALTH_URL（可用 REWRZ_HEALTH_URL 指定实际入口）"
        warn "请检查日志: sudo journalctl -u ${SERVICE_NAME%.service} -n 50"
    fi
else
    warn "未安装 curl，跳过健康检查"
fi

echo ""
echo "=========================================="
echo "  更新完成！"
echo "=========================================="
echo ""
echo "服务状态："
sudo systemctl status "$SERVICE_NAME" --no-pager -l | head -5 || true
echo ""
echo "如遇问题，查看日志："
echo "  sudo journalctl -u ${SERVICE_NAME%.service} -f"
if [ "$DO_BACKUP" = true ]; then
    echo ""
    echo "如需回滚，参考 docs/operations/UPDATE.md，备份位于: $BACKUP_DIR"
fi
echo ""
