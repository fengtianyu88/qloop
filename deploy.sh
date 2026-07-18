#!/usr/bin/env bash
# ============================================================================
# qloop — Linux 一键部署脚本
# ----------------------------------------------------------------------------
# 用法:
#   1. 编辑本脚本顶部「配置区」, 按实际环境填写
#   2. chmod +x deploy.sh
#   3. sudo ./deploy.sh           # 全新部署
#      sudo ./deploy.sh --restart # 仅重启服务
#      sudo ./deploy.sh --status  # 查看服务状态
#      sudo ./deploy.sh --stop    # 停止所有服务
#      sudo ./deploy.sh --logs    # 查看后端日志
# ----------------------------------------------------------------------------
# 支持系统: Ubuntu 20.04+ / Debian 11+ / CentOS 8+ / RHEL 8+
# ============================================================================

set -euo pipefail

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                          配 置 区 (请按需修改)                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ---------- 应用名称 (网页标题 / 顶栏 / 登录页 / 邮件签名) ----------
# "qloop" = Quality + Loop, 寓意质量与闭环融合, 测试在开发中不断循环完善
# 完整名称: 显示在浏览器标签、登录页大标题、顶栏、邮件正文
APP_NAME="qloop"
# 简短名称: 显示在侧边栏 logo、邮件主题前缀
APP_SHORT_NAME="qloop"

# ---------- 安装路径 ----------
INSTALL_DIR="/opt/qloop"                  # 项目部署根目录
VENV_DIR="$INSTALL_DIR/backend/venv"        # Python 虚拟环境目录

# ---------- 端口配置 ----------
BACKEND_PORT=8000                            # 后端 API 端口
FRONTEND_DEV_PORT=5173                       # 前端开发端口 (生产用 Nginx 80)
POSTGRES_PORT=5432                           # PostgreSQL 端口
REDIS_PORT=6379                              # Redis 端口
MINIO_API_PORT=9000                          # MinIO API 端口
MINIO_CONSOLE_PORT=9001                      # MinIO 控制台端口

# ---------- PostgreSQL ----------
PG_DB_NAME="qloop"                         # 数据库名
PG_DB_USER="qloop"                             # 数据库用户名
PG_DB_PASSWORD="qloop@2026"                    # 数据库密码 (请修改!)

# ---------- Redis ----------
REDIS_PASSWORD=""                            # Redis 密码 (空=无密码)

# ---------- MinIO ----------
MINIO_ACCESS_KEY="minioadmin"                # MinIO 访问密钥
MINIO_SECRET_KEY="minioadmin@2026"           # MinIO 秘密密钥 (请修改!)
MINIO_BUCKET="qloop"                       # 存储桶名称
MINIO_DATA_DIR="/data/minio"                 # MinIO 数据存储目录

# ---------- 应用安全 ----------
# JWT 密钥: 可用 `openssl rand -hex 32` 生成, 留空则脚本自动生成
SECRET_KEY=""
ACCESS_TOKEN_EXPIRE_MINUTES=480              # Token 过期时间 (分钟), 480=8小时

# ---------- 管理员账号 ----------
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="admin123"                   # 首次登录后请立即修改!
ADMIN_EMAIL="admin@company.com"

# ---------- SMTP 邮件 (可选, 不配置则邮件功能静默失败) ----------
SMTP_HOST="localhost"
SMTP_PORT=25
SMTP_USER=""                                 # 留空=不认证
SMTP_PASSWORD=""                             # 留空=不认证
SMTP_FROM="noreply@qloop.local"

# ---------- LLM 大模型 (可选, 也可启动后在系统页面配置) ----------
LLM_TIMEOUT=300                              # LLM 调用超时 (秒)
LLM_MAX_RETRIES=3                            # LLM 最大重试次数

# ---------- 后端监听地址 (Nginx 反代目标) ----------
# 普通 Linux 服务器: 127.0.0.1 (默认)
# WSL2 mirrored 网络模式: 10.255.255.254 (当 127.0.0.1 不可达时改此值)
BACKEND_HOST="127.0.0.1"

# ---------- LLM 大模型种子 (可选, 留空 API_KEY 则跳过该模型) ----------
# 所有模型均使用 OpenAI 兼容接口。部署后也可在「LLM 配置」页面手动增删改。
# priority 数字越小优先级越高 (主模型用小数字, 备用模型用大数字)。
LLM_MINIMAX_M3_API_BASE="https://api.minimaxi.com/v1"
LLM_MINIMAX_M3_API_KEY=""
LLM_MINIMAX_M3_MODEL="MiniMax-M3"
LLM_MINIMAX_M3_PRIORITY=10

LLM_MINIMAX_M27_API_BASE="https://api.minimaxi.com/v1"
LLM_MINIMAX_M27_API_KEY=""
LLM_MINIMAX_M27_MODEL="MiniMax-M2.7"
LLM_MINIMAX_M27_PRIORITY=20

LLM_GLM_API_BASE="https://open.bigmodel.cn/api/paas/v4"
LLM_GLM_API_KEY=""
LLM_GLM_MODEL="glm-5.2"
LLM_GLM_PRIORITY=30

LLM_DEEPSEEK_API_BASE="https://api.deepseek.com/v1"
LLM_DEEPSEEK_API_KEY=""
LLM_DEEPSEEK_MODEL="deepseek-v4-flash"
LLM_DEEPSEEK_PRIORITY=40

# ---------- 前端访问来源 (CORS, 逗号分隔) ----------
# 开发模式: http://localhost:5173 ; 生产 Nginx: http://你的域名或IP
FRONTEND_ORIGINS="http://localhost:5173,http://localhost"

# ---------- 运行用户 ----------
RUN_USER="qloop"                               # 运行服务的系统用户
RUN_GROUP="qloop"

# ---------- Node.js 版本 ----------
NODE_MAJOR=20                                # Node.js 大版本 (18/20/22)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                    以下为实现区 (一般无需修改)                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# 颜色与日志
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARN:${NC} $*"; }
err()  { echo -e "${RED}[$(date +%H:%M:%S)] ERROR:${NC} $*" >&2; }
info() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }

# 脚本所在目录 (即项目源码目录)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 检测包管理器
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v yum &>/dev/null; then
        echo "yum"
    else
        echo "unknown"
    fi
}

PKG_MGR=$(detect_pkg_manager)

# 判断是否为 root
require_root() {
    if [[ $EUID -ne 0 ]]; then
        err "请使用 root 或 sudo 运行此脚本"
        exit 1
    fi
}

# 安装系统依赖
install_system_deps() {
    log "安装系统依赖 (包管理器: $PKG_MGR) ..."

    case "$PKG_MGR" in
        apt)
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -qq
            apt-get install -y -qq \
                curl wget gnupg2 lsb-release ca-certificates \
                python3.12 python3.12-venv python3-pip \
                postgresql postgresql-contrib \
                redis-server nginx \
                >/dev/null 2>&1
            ;;
        dnf|yum)
            $PKG_MGR install -y -q \
                curl wget gnupg2 \
                python3 python3-pip \
                postgresql-server postgresql-contrib \
                redis nginx \
                >/dev/null 2>&1
            # CentOS 需初始化 PostgreSQL
            if [[ "$PKG_MGR" == "dnf" ]] && ! rpm -q postgresql-server &>/dev/null; then
                postgresql-setup --initdb 2>/dev/null || true
            fi
            ;;
    esac

    # 安装 Node.js (通过 NodeSource 官方源, 确保版本正确)
    if ! command -v node &>/dev/null || [[ "$(node -v 2>/dev/null | cut -d. -f1 | tr -d v)" -lt "$NODE_MAJOR" ]]; then
        log "安装 Node.js $NODE_MAJOR ..."
        curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - >/dev/null 2>&1
        if [[ "$PKG_MGR" == "apt" ]]; then
            apt-get install -y -qq nodejs >/dev/null 2>&1
        else
            $PKG_MGR install -y -q nodejs >/dev/null 2>&1
        fi
    fi

    log "系统依赖安装完成: Python $(python3 --version 2>&1 | awk '{print $2}'), Node $(node -v 2>&1)"
}

# 安装 MinIO
install_minio() {
    if command -v minio &>/dev/null; then
        log "MinIO 已安装, 跳过"
        return
    fi
    log "下载安装 MinIO ..."
    wget -q -O /usr/local/bin/minio "https://dl.min.io/server/minio/release/linux-amd64/minio"
    chmod +x /usr/local/bin/minio
    log "MinIO 安装完成"
}

# 创建运行用户
create_run_user() {
    if ! id "$RUN_USER" &>/dev/null; then
        log "创建运行用户: $RUN_USER"
        useradd -r -s /sbin/nologin "$RUN_USER"
    fi
}

# 配置 PostgreSQL
setup_postgres() {
    log "配置 PostgreSQL ..."

    # 启动 PostgreSQL
    case "$PKG_MGR" in
        apt) systemctl enable --now postgresql >/dev/null 2>&1 ;;
        *)   systemctl enable --now postgresql >/dev/null 2>&1
             systemctl start postgresql >/dev/null 2>&1 ;;
    esac

    # 创建数据库和用户 (幂等)
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$PG_DB_USER'" | grep -q 1 \
        || sudo -u postgres psql -c "CREATE USER $PG_DB_USER WITH PASSWORD '$PG_DB_PASSWORD';" >/dev/null

    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$PG_DB_NAME'" | grep -q 1 \
        || sudo -u postgres psql -c "CREATE DATABASE $PG_DB_NAME OWNER $PG_DB_USER;" >/dev/null

    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $PG_DB_NAME TO $PG_DB_USER;" >/dev/null 2>&1
    sudo -u postgres psql -d "$PG_DB_NAME" -c "GRANT ALL ON SCHEMA public TO $PG_DB_USER;" >/dev/null 2>&1

    log "PostgreSQL 配置完成 (库: $PG_DB_NAME, 用户: $PG_DB_USER)"
}

# 配置 Redis
setup_redis() {
    log "配置 Redis ..."

    systemctl enable --now redis-server >/dev/null 2>&1 || systemctl enable --now redis >/dev/null 2>&1

    # 设置密码 (如配置了)
    if [[ -n "$REDIS_PASSWORD" ]]; then
        local redis_conf=""
        [[ -f /etc/redis/redis.conf ]] && redis_conf="/etc/redis/redis.conf"
        [[ -f /etc/redis.conf ]] && redis_conf="/etc/redis.conf"
        if [[ -n "$redis_conf" ]]; then
            sed -i "s/^# requirepass .*/requirepass $REDIS_PASSWORD/" "$redis_conf"
            grep -q "^requirepass" "$redis_conf" || echo "requirepass $REDIS_PASSWORD" >> "$redis_conf"
            systemctl restart redis-server >/dev/null 2>&1 || systemctl restart redis >/dev/null 2>&1
        fi
    fi

    log "Redis 配置完成"
}

# 部署项目源码
deploy_source() {
    log "部署项目源码到 $INSTALL_DIR ..."

    mkdir -p "$INSTALL_DIR"
    # 复制源码 (排除 venv/node_modules/.git)
    rsync -a --exclude='venv/' --exclude='node_modules/' --exclude='.git/' \
          --exclude='__pycache__/' --exclude='*.pyc' --exclude='dist/' \
          "$SCRIPT_DIR/" "$INSTALL_DIR/"

    chown -R "$RUN_USER:$RUN_GROUP" "$INSTALL_DIR"

    log "源码部署完成"
}

# 创建 Python 虚拟环境并安装后端依赖
setup_backend() {
    log "配置后端 Python 环境 ..."

    python3 -m venv "$VENV_DIR"
    chown -R "$RUN_USER:$RUN_GROUP" "$VENV_DIR"

    # 升级 pip 并安装依赖 (以 RUN_USER 身份)
    sudo -u "$RUN_USER" "$VENV_DIR/bin/pip" install --upgrade pip -q
    sudo -u "$RUN_USER" "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q

    log "后端依赖安装完成"
}

# 生成 .env 配置文件
generate_env() {
    log "生成后端 .env 配置 ..."

    # 自动生成 SECRET_KEY (如未配置)
    if [[ -z "$SECRET_KEY" ]]; then
        SECRET_KEY=$(openssl rand -hex 32)
        info "已自动生成 SECRET_KEY"
    fi

    # 构建 Redis URL
    local redis_url="redis://localhost:$REDIS_PORT/0"
    [[ -n "$REDIS_PASSWORD" ]] && redis_url="redis://:${REDIS_PASSWORD}@localhost:${REDIS_PORT}/0"

    # URL-encode special chars in DB password (e.g. @ -> %40)
    local PG_DB_PASSWORD_URL="${PG_DB_PASSWORD//@/%40}"

    cat > "$INSTALL_DIR/backend/.env" <<EOF
# ═══════════════════════════════════════════════════
# qloop 后端配置 (由 deploy.sh 自动生成)
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')
# ═══════════════════════════════════════════════════

# 应用
APP_NAME=$APP_NAME
APP_SHORT_NAME=$APP_SHORT_NAME
SECRET_KEY=$SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=$ACCESS_TOKEN_EXPIRE_MINUTES

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://$PG_DB_USER:$PG_DB_PASSWORD_URL@localhost:$POSTGRES_PORT/$PG_DB_NAME

# Redis
REDIS_URL=$redis_url

# MinIO
MINIO_ENDPOINT=localhost:$MINIO_API_PORT
MINIO_ACCESS_KEY=$MINIO_ACCESS_KEY
MINIO_SECRET_KEY=$MINIO_SECRET_KEY
MINIO_BUCKET=$MINIO_BUCKET
MINIO_SECURE=false

# SMTP
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASSWORD=$SMTP_PASSWORD
SMTP_FROM=$SMTP_FROM

# LLM
LLM_TIMEOUT=$LLM_TIMEOUT
LLM_MAX_RETRIES=$LLM_MAX_RETRIES
EOF

    chmod 600 "$INSTALL_DIR/backend/.env"
    chown "$RUN_USER:$RUN_GROUP" "$INSTALL_DIR/backend/.env"

    log ".env 配置文件已生成"
}

# 更新后端 CORS 配置
update_cors() {
    log "更新后端 CORS 配置 ..."

    local main_py="$INSTALL_DIR/backend/app/main.py"
    # 将 allow_origins 替换为配置的来源
    local origins_json=$(echo "$FRONTEND_ORIGINS" | tr ',' '\n' | sed 's/^/"/' | sed 's/$/"/' | paste -sd, -)
    sed -i "s|allow_origins=\[.*\]|allow_origins=[$origins_json]|" "$main_py"

    log "CORS 已更新为: $FRONTEND_ORIGINS"
}

# 初始化数据库表并创建管理员
init_database() {
    log "初始化数据库表 ..."

    cd "$INSTALL_DIR/backend"
    sudo -u "$RUN_USER" "$VENV_DIR/bin/python" -c "
import asyncio
from app.database import engine, Base
from app.models import *

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('数据库表创建成功')

asyncio.run(init())
"

    log "创建超级管理员账号 ..."
    sudo -u "$RUN_USER" "$VENV_DIR/bin/python" -c "
import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models.user import User, SystemRole
from app.utils.security import hash_password

async def create_admin():
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == '$ADMIN_USERNAME'))
        if result.scalar_one_or_none() is None:
            admin = User(
                username='$ADMIN_USERNAME',
                email='$ADMIN_EMAIL',
                full_name='超级管理员',
                hashed_password=hash_password('$ADMIN_PASSWORD'),
                system_role=SystemRole.SUPER_ADMIN,
            )
            db.add(admin)
            await db.commit()
            print('超级管理员创建成功: $ADMIN_USERNAME / $ADMIN_PASSWORD')
        else:
            print('管理员账号已存在, 跳过')

asyncio.run(create_admin())
"
    cd - >/dev/null
}

# 种子 LLM 模型配置 (幂等: 按 name 查重, 已存在则跳过; API_KEY 为空则跳过)
seed_llm_models() {
    log "种子 LLM 模型配置 ..."

    cd "$INSTALL_DIR/backend"
    # 通过 env 显式传递变量给 sudo -u 子进程 (quoted heredoc 不做 shell 插值,
    # Python 端用 os.environ.get 读取, 避免 API Key 中的特殊字符被 shell 解释)
    sudo -u "$RUN_USER" env \
        LLM_MINIMAX_M3_API_BASE="$LLM_MINIMAX_M3_API_BASE" \
        LLM_MINIMAX_M3_API_KEY="$LLM_MINIMAX_M3_API_KEY" \
        LLM_MINIMAX_M3_MODEL="$LLM_MINIMAX_M3_MODEL" \
        LLM_MINIMAX_M3_PRIORITY="$LLM_MINIMAX_M3_PRIORITY" \
        LLM_MINIMAX_M27_API_BASE="$LLM_MINIMAX_M27_API_BASE" \
        LLM_MINIMAX_M27_API_KEY="$LLM_MINIMAX_M27_API_KEY" \
        LLM_MINIMAX_M27_MODEL="$LLM_MINIMAX_M27_MODEL" \
        LLM_MINIMAX_M27_PRIORITY="$LLM_MINIMAX_M27_PRIORITY" \
        LLM_GLM_API_BASE="$LLM_GLM_API_BASE" \
        LLM_GLM_API_KEY="$LLM_GLM_API_KEY" \
        LLM_GLM_MODEL="$LLM_GLM_MODEL" \
        LLM_GLM_PRIORITY="$LLM_GLM_PRIORITY" \
        LLM_DEEPSEEK_API_BASE="$LLM_DEEPSEEK_API_BASE" \
        LLM_DEEPSEEK_API_KEY="$LLM_DEEPSEEK_API_KEY" \
        LLM_DEEPSEEK_MODEL="$LLM_DEEPSEEK_MODEL" \
        LLM_DEEPSEEK_PRIORITY="$LLM_DEEPSEEK_PRIORITY" \
        "$VENV_DIR/bin/python" <<'PYEOF'
import asyncio, os
from sqlalchemy import select
from app.database import async_session
from app.models.review import LLMModel, LLMProtocol

# (显示名, api_base 环境变量, api_key 环境变量, model_name 环境变量, priority 环境变量)
SEEDS = [
    ("minimax-M3",        "LLM_MINIMAX_M3_API_BASE",   "LLM_MINIMAX_M3_API_KEY",   "LLM_MINIMAX_M3_MODEL",   "LLM_MINIMAX_M3_PRIORITY"),
    ("minimax-M2.7",      "LLM_MINIMAX_M27_API_BASE",  "LLM_MINIMAX_M27_API_KEY",  "LLM_MINIMAX_M27_MODEL",  "LLM_MINIMAX_M27_PRIORITY"),
    ("GLM-5.2",           "LLM_GLM_API_BASE",          "LLM_GLM_API_KEY",          "LLM_GLM_MODEL",          "LLM_GLM_PRIORITY"),
    ("Deepseek-V4-flash", "LLM_DEEPSEEK_API_BASE",     "LLM_DEEPSEEK_API_KEY",     "LLM_DEEPSEEK_MODEL",     "LLM_DEEPSEEK_PRIORITY"),
]

async def seed():
    async with async_session() as db:
        for name, base_env, key_env, model_env, pri_env in SEEDS:
            api_base = os.environ.get(base_env, "")
            api_key  = os.environ.get(key_env, "")
            model    = os.environ.get(model_env, "")
            priority = int(os.environ.get(pri_env, "100") or "100")
            if not api_key:
                print(f"  跳过 {name}: API_KEY 为空")
                continue
            exists = await db.execute(select(LLMModel).where(LLMModel.name == name))
            if exists.scalar_one_or_none() is not None:
                print(f"  跳过 {name}: 已存在")
                continue
            db.add(LLMModel(
                name=name, protocol=LLMProtocol.OPENAI,
                api_base=api_base, api_key=api_key,
                model_name=model, is_active=True, priority=priority,
            ))
            print(f"  注册 {name} ({model}) priority={priority}")
        await db.commit()
asyncio.run(seed())
PYEOF
    cd - >/dev/null
    log "LLM 模型种子完成"
}

# 执行数据库迁移 (新增字段/索引等, 幂等)
run_migrations() {
    log "执行数据库迁移 (幂等) ..."

    cd "$INSTALL_DIR/backend"
    sudo -u "$RUN_USER" "$VENV_DIR/bin/python" <<'PYMIGRATE'
import asyncio
from sqlalchemy import text
from app.database import engine

MIGRATIONS = [
    # v1.2.0: 为 releases 表添加上传人/上传时间字段 (SOX 审计追溯)
    ("releases_code_package_uploaded_by",
     "ALTER TABLE releases ADD COLUMN IF NOT EXISTS code_package_uploaded_by UUID REFERENCES users(id)"),
    ("releases_code_package_uploaded_at",
     "ALTER TABLE releases ADD COLUMN IF NOT EXISTS code_package_uploaded_at TIMESTAMPTZ"),
    ("releases_test_report_uploaded_by",
     "ALTER TABLE releases ADD COLUMN IF NOT EXISTS test_report_uploaded_by UUID REFERENCES users(id)"),
    ("releases_test_report_uploaded_at",
     "ALTER TABLE releases ADD COLUMN IF NOT EXISTS test_report_uploaded_at TIMESTAMPTZ"),
    ("releases_review_report_uploaded_by",
     "ALTER TABLE releases ADD COLUMN IF NOT EXISTS review_report_uploaded_by UUID REFERENCES users(id)"),
    ("releases_review_report_uploaded_at",
     "ALTER TABLE releases ADD COLUMN IF NOT EXISTS review_report_uploaded_at TIMESTAMPTZ"),
]

async def migrate():
    async with engine.begin() as conn:
        for name, sql in MIGRATIONS:
            try:
                await conn.execute(text(sql))
                print(f"  OK: {name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  SKIP (exists): {name}")
                else:
                    print(f"  WARN: {name} -> {e}")

        # Backfill uploaded_by from audit_logs (best-effort)
        backfill_sqls = [
            ("code_package", "upload_code_package"),
            ("test_report", "upload_test_report"),
            ("review_report", "upload_review_report"),
        ]
        for col, action in backfill_sqls:
            try:
                result = await conn.execute(text(f"""
                    UPDATE releases r
                    SET {col}_uploaded_by = a.user_id,
                        {col}_uploaded_at = a.created_at
                    FROM audit_logs a
                    WHERE a.resource_id::text = r.id::text
                      AND a.action = '{action}'
                      AND r.{col}_path IS NOT NULL
                      AND r.{col}_uploaded_by IS NULL
                """))
                if result.rowcount > 0:
                    print(f"  BACKFILL: {col} ({result.rowcount} rows)")
            except Exception as e:
                print(f"  BACKFILL WARN: {col} -> {e}")

    print("数据库迁移完成")

asyncio.run(migrate())
PYMIGRATE

    log "数据库迁移完成"
}

# 构建前端
build_frontend() {
    log "构建前端 ..."

    cd "$INSTALL_DIR/frontend"
    npm install --silent 2>/dev/null
    # 修复权限: npm install 以 root 运行, 但 build 以 RUN_USER 运行
    # 必须在 npm install 之后执行, 并确保 .tmp 目录可写 (vue-tsc 需要写入 tsbuildinfo)
    chown -R "$RUN_USER:$RUN_GROUP" "$INSTALL_DIR/frontend"
    mkdir -p "$INSTALL_DIR/frontend/node_modules/.tmp"
    chown -R "$RUN_USER:$RUN_GROUP" "$INSTALL_DIR/frontend/node_modules/.tmp"

    # 通过环境变量向 Vite 注入应用名称 (构建期静态内联到产物中)
    # 部署者在配置区修改 APP_NAME / APP_SHORT_NAME 即可同步更新网页标题
    export VITE_APP_TITLE="$APP_NAME"
    export VITE_APP_SHORT_NAME="$APP_SHORT_NAME"
    log "前端标题注入: VITE_APP_TITLE='$APP_NAME', VITE_APP_SHORT_NAME='$APP_SHORT_NAME'"

    # 构建生产版本 (不抑制 stderr, 失败时立即终止)
    if ! sudo -u "$RUN_USER" \
        VITE_APP_TITLE="$APP_NAME" \
        VITE_APP_SHORT_NAME="$APP_SHORT_NAME" \
        bash -c "cd $INSTALL_DIR/frontend && npm run build"; then
        err "前端构建失败 (npm run build), 请检查上方输出"
        err "常见原因: node_modules/.tmp 权限不足 / TypeScript 类型错误 / 依赖缺失"
        return 1
    fi

    # 复制到 Nginx 目录
    mkdir -p /var/www/qloop
    rm -rf /var/www/qloop/*
    cp -r dist/* /var/www/qloop/
    chown -R www-data:www-data /var/www/qloop 2>/dev/null || \
        chown -R nginx:nginx /var/www/qloop 2>/dev/null || true

    # 校验 HTML 标题占位符已被 Vite 替换
    if grep -q '%VITE_APP_TITLE%' /var/www/qloop/index.html; then
        warn "index.html 仍含 %VITE_APP_TITLE% 占位符, Vite 环境变量替换未生效"
    fi

    log "前端构建完成, 产物部署到 /var/www/qloop"
}

# 配置 Nginx
setup_nginx() {
    log "配置 Nginx ..."

    cat > /etc/nginx/sites-available/qloop <<'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 500M;

    # 前端静态文件
    location / {
        root /var/www/qloop;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # index.html 不缓存，避免浏览器引用过期的 chunk 文件名导致模块加载失败
    location = /index.html {
        root /var/www/qloop;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        expires 0;
    }

    # 带 hash 的 chunk 文件可以长期缓存
    location /assets/ {
        root /var/www/qloop;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # API 反向代理到后端
    location /api/ {
        proxy_pass http://BACKEND_HOST:BACKEND_PORT;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        client_max_body_size 500M;
    }
}
EOF
    sed -i "s/BACKEND_HOST/$BACKEND_HOST/" /etc/nginx/sites-available/qloop
    sed -i "s/BACKEND_PORT/$BACKEND_PORT/" /etc/nginx/sites-available/qloop

    ln -sf /etc/nginx/sites-available/qloop /etc/nginx/sites-enabled/qloop
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null

    nginx -t 2>/dev/null
    systemctl reload nginx
    systemctl enable nginx >/dev/null 2>&1

    log "Nginx 配置完成 (端口 80 → 前端 + 代理 $BACKEND_HOST:$BACKEND_PORT)"
}

# 创建 systemd 服务
create_systemd_services() {
    log "创建 systemd 服务 ..."

    # ---------- MinIO ----------
    mkdir -p "$MINIO_DATA_DIR"
    chown -R "$RUN_USER:$RUN_GROUP" "$MINIO_DATA_DIR"

    cat > /etc/systemd/system/qloop-minio.service <<EOF
[Unit]
Description=$APP_SHORT_NAME MinIO Object Storage
After=network.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
ExecStart=/usr/local/bin/minio server $MINIO_DATA_DIR \\
    --address ":$MINIO_API_PORT" \\
    --console-address ":$MINIO_CONSOLE_PORT"
Environment="MINIO_ROOT_USER=$MINIO_ACCESS_KEY"
Environment="MINIO_ROOT_PASSWORD=$MINIO_SECRET_KEY"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # ---------- 后端 ----------
    cat > /etc/systemd/system/qloop-backend.service <<EOF
[Unit]
Description=$APP_SHORT_NAME Backend API
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$INSTALL_DIR/backend
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --workers 4
Restart=always
RestartSec=5
EnvironmentFile=$INSTALL_DIR/backend/.env

[Install]
WantedBy=multi-user.target
EOF

    # ---------- Celery ----------
    cat > /etc/systemd/system/qloop-celery.service <<EOF
[Unit]
Description=$APP_SHORT_NAME Celery Worker
After=network.target redis-server.service qloop-backend.service

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$INSTALL_DIR/backend
ExecStart=$VENV_DIR/bin/celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
Restart=always
RestartSec=5
EnvironmentFile=$INSTALL_DIR/backend/.env

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable qloop-minio qloop-backend qloop-celery >/dev/null 2>&1

    log "systemd 服务已创建 (qloop-minio / qloop-backend / qloop-celery)"
}

# 启动所有服务
start_services() {
    log "启动服务 ..."

    systemctl start qloop-minio
    sleep 2  # 等待 MinIO 就绪

    systemctl start qloop-backend
    sleep 3  # 等待后端就绪

    systemctl start qloop-celery

    log "所有服务已启动"
}

# 停止所有服务
stop_services() {
    log "停止服务 ..."
    systemctl stop qloop-celery qloop-backend qloop-minio 2>/dev/null || true
    log "服务已停止"
}

# 重启所有服务
restart_services() {
    log "重启服务 ..."
    systemctl restart qloop-minio
    sleep 2
    systemctl restart qloop-backend
    sleep 3
    systemctl restart qloop-celery
    log "服务已重启"
}

# 验证部署
verify_deployment() {
    log "验证部署 ..."

    local all_ok=true

    # 后端
    if curl -sf "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
        info "  [OK] 后端 API (端口 $BACKEND_PORT)"
    else
        err "  [FAIL] 后端 API 不可达"
        all_ok=false
    fi

    # 前端 (通过 Nginx)
    if curl -sf "http://localhost/" >/dev/null 2>&1; then
        info "  [OK] 前端 (Nginx 端口 80)"
    else
        err "  [FAIL] 前端不可达"
        all_ok=false
    fi

    # PostgreSQL
    if sudo -u postgres psql -tAc "SELECT 1" >/dev/null 2>&1; then
        info "  [OK] PostgreSQL"
    else
        err "  [FAIL] PostgreSQL"
        all_ok=false
    fi

    # Redis
    if redis-cli ping >/dev/null 2>&1; then
        info "  [OK] Redis"
    else
        err "  [FAIL] Redis"
        all_ok=false
    fi

    # MinIO
    if curl -sf "http://localhost:$MINIO_API_PORT/minio/health/live" >/dev/null 2>&1; then
        info "  [OK] MinIO (端口 $MINIO_API_PORT)"
    else
        err "  [FAIL] MinIO"
        all_ok=false
    fi

    # Celery
    if systemctl is-active --quiet qloop-celery; then
        info "  [OK] Celery Worker"
    else
        err "  [FAIL] Celery Worker"
        all_ok=false
    fi

    echo ""
    if $all_ok; then
        echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}  ✓ 部署成功! 所有服务运行正常${NC}"
        echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "  访问地址:  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)"
        echo "  管理员:    $ADMIN_USERNAME / $ADMIN_PASSWORD"
        echo "  MinIO 控制台: http://localhost:$MINIO_CONSOLE_PORT ($MINIO_ACCESS_KEY / $MINIO_SECRET_KEY)"
        echo ""
        echo "  常用命令:"
        echo "    sudo ./deploy.sh --status   # 查看服务状态"
        echo "    sudo ./deploy.sh --restart  # 重启服务"
        echo "    sudo ./deploy.sh --stop     # 停止服务"
        echo "    sudo ./deploy.sh --logs     # 查看后端日志"
        echo ""
        warn "  请尽快登录系统修改管理员密码!"
        warn "  SMTP 和 LLM 需在 .env 或系统页面中配置后才能使用"
    else
        echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${RED}  ✗ 部署存在问题, 请检查上方 [FAIL] 项${NC}"
        echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "  排查命令:"
        echo "    sudo ./deploy.sh --logs     # 查看后端日志"
        echo "    sudo journalctl -u qloop-backend -n 50  # 查看后端 systemd 日志"
        echo "    sudo journalctl -u qloop-celery -n 50   # 查看 Celery 日志"
        exit 1
    fi
}

# 显示状态
show_status() {
    echo -e "${BLUE}════════════════ $APP_NAME 服务状态 ══════════════════${NC}"
    for svc in qloop-minio qloop-backend qloop-celery nginx postgresql redis-server; do
        local state=$(systemctl is-active "$svc" 2>/dev/null || echo "未安装")
        if [[ "$state" == "active" ]]; then
            printf "  ${GREEN}%-15s${NC} %s\n" "$svc" "✓ 运行中"
        else
            printf "  ${RED}%-15s${NC} %s\n" "$svc" "✗ $state"
        fi
    done
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
}

# 查看日志
show_logs() {
    echo "后端日志 (最近 50 行), Ctrl+C 退出 ..."
    echo ""
    journalctl -u qloop-backend -n 50 --no-pager -f
}

# 显示帮助
show_help() {
    cat <<EOF
$APP_NAME — 一键部署脚本

用法: sudo ./deploy.sh [命令]

命令:
  (无参数)    全新部署 (安装依赖 + 配置 + 启动)
  --restart   重启所有服务
  --status    查看服务状态
  --stop      停止所有服务
  --logs      查看后端日志 (实时跟踪)
  --help      显示此帮助信息

首次部署前, 请编辑脚本顶部「配置区」填写实际参数。

服务端口:
  前端 (Nginx):   80
  后端 API:        $BACKEND_PORT
  PostgreSQL:      $POSTGRES_PORT
  Redis:           $REDIS_PORT
  MinIO API:       $MINIO_API_PORT
  MinIO 控制台:    $MINIO_CONSOLE_PORT
EOF
}

# ============================================================================
# 主流程
# ============================================================================
main() {
    local cmd="${1:-deploy}"

    case "$cmd" in
        --help|-h) show_help; exit 0 ;;
        --status)  show_status; exit 0 ;;
        --stop)    require_root; stop_services; exit 0 ;;
        --restart) require_root; restart_services; sleep 2; show_status; exit 0 ;;
        --logs)    show_logs; exit 0 ;;
        deploy|"") ;;
        *) err "未知命令: $cmd"; show_help; exit 1 ;;
    esac

    require_root

    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  $APP_NAME — 一键部署${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    # 确认配置
    info "应用名称: $APP_NAME (简短: $APP_SHORT_NAME)"
    info "部署目录: $INSTALL_DIR"
    info "数据库: $PG_DB_USER@localhost:$POSTGRES_PORT/$PG_DB_NAME"
    info "管理员: $ADMIN_USERNAME (首次登录后请改密)"
    echo ""
    read -p "确认以上配置并开始部署? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { info "已取消"; exit 0; }
    echo ""

    # 执行部署步骤
    install_system_deps
    install_minio
    create_run_user
    setup_postgres
    setup_redis
    deploy_source
    setup_backend
    generate_env
    update_cors
    init_database
    run_migrations
    seed_llm_models
    build_frontend
    setup_nginx
    create_systemd_services
    start_services

    echo ""
    verify_deployment
}

main "$@"
