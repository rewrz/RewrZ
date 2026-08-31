#!/bin/bash
# RewrZ 一键更新部署脚本
#
# 用法:
#   ./update.sh                 更新到当前分支最新
#   ./update.sh v0.9.2          更新到指定标签或提交
#   ./update.sh --no-backup     跳过更新前自动备份
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
TARGET_REF=""
DO_BACKUP=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "$1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

for arg in "$@"; do
    case "$arg" in
        --no-backup)
            DO_BACKUP=false
            ;;
        -h|--help)
            sed -n '2,12p' "$0"
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

    if [ -f ".env" ]; then
        cp .env "$BACKUP_DIR/.env"
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
        cp "$DB_PATH" "$BACKUP_DIR/$(basename "$DB_PATH")"
        ok "数据库已备份: $DB_PATH"
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
.venv/bin/pip install -q -r requirements.txt
ok "依赖已就绪"

# 7. 执行数据库迁移
echo ""
echo ">>> 执行数据库迁移..."
.venv/bin/alembic upgrade head
ok "数据库迁移完成"

# 8. 检查 .env 是否存在重复配置项
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

# 9. 提示前端产物重建
if [ "$IN_GIT_REPO" = true ] && [ "$CHANGED" = true ] && [ -n "$OLD_REV" ]; then
    FRONTEND_CHANGED="$(git diff --name-only "$OLD_REV" HEAD -- rewrz/templates tailwind.config.js package.json 2>/dev/null || true)"
    if [ -n "$FRONTEND_CHANGED" ]; then
        warn "检测到模板或 Tailwind 配置变更："
        echo "$FRONTEND_CHANGED" | sed 's/^/       - /'
        warn "若仓库未提交最新 CSS 产物，请执行: npm install && npm run build:css"
    fi
fi

# 10. 重启服务
echo ""
echo ">>> 重启服务..."
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    sudo systemctl restart "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
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

# 11. 重新加载 Nginx（仅在配置通过检测时）
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

# 12. 最小烟测
echo ""
echo ">>> 最小烟测..."
if command -v curl >/dev/null 2>&1; then
    if curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 "$HEALTH_URL" >/dev/null 2>&1; then
        ok "健康检查通过: $HEALTH_URL"
    else
        warn "健康检查未通过: $HEALTH_URL（可用 REWRZ_HEALTH_URL 指定实际入口）"
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
