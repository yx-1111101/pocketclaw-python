#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# PocketClaw Gateway 连接器安装脚本
#
# 在目标机器上运行：
#   curl -fsSL https://yixuan-site.cn/install/gateway | bash
#
# 该脚本会：
#   1. 检测 OpenClaw；未安装则自动安装（Node.js + npm install openclaw@latest）
#   2. 安装 Python 依赖（websockets、httpx）
#   3. 下载 pocketclaw-device 连接器
#   4. 配置并启动连接器
#      → 启动后自动向云端注册，打印 8 位配对码
#      → 在 Web 管理界面输入配对码完成绑定
#
# 注：外部 Gateway 设备号（gw-xxx）由云端分配，与 OpenClaw 自身的设备号无关
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

CLOUD_API_URL="${POCKETCLAW_CLOUD_URL:-https://yixuan-site.cn}"
INSTALL_DIR="$HOME/.pocketclaw-gateway"

echo ""
echo "═══════════════════════════════════════════════"
echo "  PocketClaw Gateway 连接器安装"
echo "  云端地址: $CLOUD_API_URL"
echo "═══════════════════════════════════════════════"
echo ""

# ── 1. 检测/安装 OpenClaw ─────────────────────────────────────────────────────
echo "[1/4] 检测 OpenClaw..."

OPENCLAW_CONFIGURED=true  # 已安装的默认视为已配置

if command -v openclaw &>/dev/null; then
    echo "  ✓ OpenClaw 已安装（将作为本地运行时使用）"
else
    echo "  ℹ OpenClaw 未安装，正在安装..."

    # 基础系统依赖（仅外部 Gateway 所需的最小集）
    sudo apt-get update -qq
    sudo apt-get install -y -qq curl ca-certificates python3

    # Node.js（openclaw 通过 npm 安装）
    INSTALL_NODE=false
    if command -v node &>/dev/null; then
        NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
        if [ "$NODE_VER" -ge 18 ]; then
            echo "  ✓ Node.js $(node -v) 已安装"
        else
            echo "  Node.js 版本过低（$(node -v)），升级中..."
            INSTALL_NODE=true
        fi
    else
        echo "  安装 Node.js 22..."
        INSTALL_NODE=true
    fi

    if [ "$INSTALL_NODE" = true ]; then
        sudo mkdir -p /etc/apt/keyrings
        curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | \
            sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg 2>/dev/null
        echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" | \
            sudo tee /etc/apt/sources.list.d/nodesource.list > /dev/null
        sudo apt-get update -qq
        sudo apt-get install -y -qq nodejs
        echo "  ✓ Node.js $(node -v) 安装完成"
    fi

    # npm 全局目录（避免 sudo 权限问题）
    if [ ! -d "$HOME/.npm-global" ]; then
        mkdir -p "$HOME/.npm-global"
        npm config set prefix "$HOME/.npm-global"
    fi
    export PATH="$HOME/.npm-global/bin:$PATH"
    if ! grep -q '.npm-global' "$HOME/.bashrc" 2>/dev/null; then
        echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> "$HOME/.bashrc"
    fi

    # 安装 openclaw CLI
    npm install -g "openclaw@latest" \
        || { echo "  ✗ openclaw 安装失败，请检查网络或手动安装 npm 包"; exit 1; }
    echo "  ✓ OpenClaw 安装完成"

    # 询问是否立即配置（模型、API 密钥等）
    # 注：curl | bash 时 stdin 是管道，需通过 /dev/tty 读取终端输入
    echo ""
    echo "  建议现在完成 OpenClaw 初始配置（模型、API 密钥等）。"
    echo "  跳过后也可运行 'openclaw configure' 单独完成。"
    printf "  立即配置 OpenClaw? [Y/n] "
    read -r _configure_choice </dev/tty 2>/dev/null || _configure_choice="n"
    echo ""
    if [[ "${_configure_choice:-y}" =~ ^[Yy]$ ]] || [ -z "$_configure_choice" ]; then
        openclaw setup 2>/dev/null || true
        openclaw configure </dev/tty
    else
        echo "  ℹ 跳过配置，连接器仍可正常启动和配对。"
        OPENCLAW_CONFIGURED=false
    fi
fi

# ── 2. 检测 Python ────────────────────────────────────────────────────────────
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "")
if [ -z "$PYTHON" ]; then
    echo ""
    echo "  ✗ 错误：未找到 Python 3，请先安装："
    echo "    sudo apt install python3  # Debian/Ubuntu"
    echo "    brew install python3      # macOS"
    exit 1
fi
PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✓ Python $PY_VER"

# ── 3. 安装 Python 依赖 ───────────────────────────────────────────────────────
echo "[2/4] 安装 Python 依赖..."

if $PYTHON -c "import websockets, httpx" 2>/dev/null; then
    echo "  ✓ websockets、httpx 已安装，跳过"
else
    # 确保 pip 可用（Ubuntu 上可能未预装）
    if ! $PYTHON -m pip --version &>/dev/null; then
        echo "  ℹ pip 未安装，正在通过 apt 安装..."
        sudo apt-get install -y python3-pip \
            || { echo "  ✗ 无法安装 pip，请手动运行: sudo apt install python3-pip"; exit 1; }
    fi
    $PYTHON -m pip install --quiet --user websockets httpx 2>/dev/null \
        || $PYTHON -m pip install --quiet websockets httpx 2>/dev/null \
        || { echo "  ✗ pip 安装失败，请手动运行: pip install websockets httpx"; exit 1; }
    echo "  ✓ websockets、httpx 已就绪"
fi

# ── 4. 下载连接器 ─────────────────────────────────────────────────────────────
echo "[3/4] 下载 Gateway 连接器..."

mkdir -p "$INSTALL_DIR"

for FILE in reverse_proxy.py heartbeat.py; do
    curl -fsSL "$CLOUD_API_URL/downloads/gateway/$FILE" -o "$INSTALL_DIR/$FILE" \
        || { echo "  ✗ 下载 $FILE 失败，请检查网络连接"; exit 1; }
done

# routes.json 可选（无则使用默认路由）
curl -fsSL "$CLOUD_API_URL/downloads/gateway/routes.json" -o "$INSTALL_DIR/routes.json" 2>/dev/null || true

echo "  ✓ 连接器下载完成: $INSTALL_DIR"

# ── 写入/更新配置 ─────────────────────────────────────────────────────────────
CONFIG_FILE="$INSTALL_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" << EOF
{
  "cloud_api_url": "$CLOUD_API_URL"
}
EOF
    echo "  ✓ 配置文件已创建: $CONFIG_FILE"
else
    $PYTHON - << EOF
import json
p = '$CONFIG_FILE'
cfg = json.load(open(p))
cfg['cloud_api_url'] = '$CLOUD_API_URL'
json.dump(cfg, open(p, 'w'), indent=2, ensure_ascii=False)
print("  ✓ 配置文件已更新: $p")
EOF
fi

# ── 5. 启动连接器 ─────────────────────────────────────────────────────────────
echo "[4/4] 启动 Gateway 连接器..."
echo ""
echo "═══════════════════════════════════════════════"
echo "  连接器启动后会显示 8 位配对码（如 A3BF-K92M）"
echo "  请在 Web 管理界面 > 添加外部 Gateway 中输入"
echo "═══════════════════════════════════════════════"
if [ "${OPENCLAW_CONFIGURED:-true}" = false ]; then
    echo ""
    echo "  ⚠ 提醒：OpenClaw 尚未配置，配对完成后 AI 对话功能暂不可用。"
    echo "    请在方便时运行：openclaw configure"
fi
echo ""

cd "$INSTALL_DIR"
exec $PYTHON reverse_proxy.py
