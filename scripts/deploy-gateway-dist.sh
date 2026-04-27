#!/bin/bash
# 将 pocketclaw-device 的关键文件部署到 gateway-dist/ 目录，
# 供 /install/gateway 和 /downloads/gateway/ 端点提供下载。
#
# 在 pocketclaw-python 目录下运行：
#   bash scripts/deploy-gateway-dist.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/../gateway-dist"
DEVICE_DIR="${POCKETCLAW_DEVICE_DIR:-$HOME/pocketclaw-device}"

mkdir -p "$DIST_DIR"

# 复制 daemon 文件（install-gateway.sh 直接在 gateway-dist/ 下维护，无需复制）
cp "$DEVICE_DIR/reverse_proxy.py" "$DIST_DIR/"
cp "$DEVICE_DIR/heartbeat.py" "$DIST_DIR/"
[ -f "$DEVICE_DIR/routes.json" ] && cp "$DEVICE_DIR/routes.json" "$DIST_DIR/" || true

echo "Gateway dist 部署完成: $DIST_DIR"
ls -lh "$DIST_DIR"
