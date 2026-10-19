#!/usr/bin/env bash
# FM 网络电台 - Ubuntu 启动脚本
# 用法: ./run.sh   （可用环境变量 PORT 指定端口，默认 8000）
set -euo pipefail
cd "$(dirname "$0")"

export PORT="${PORT:-8000}"

# Force direct connection: never use system/env proxy (Clash Verge, etc.)
export RB_PROXY_MODE="${RB_PROXY_MODE:-direct}"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

if ! command -v python3 >/dev/null 2>&1; then
  echo "错误：未找到 python3。请先安装："
  echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[1/3] 创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/3] 安装依赖（首次运行需要联网）..."
pip install -q -r requirements.txt

echo "[3/3] 启动 FM 电台服务，端口 $PORT ..."
echo "本地访问:  http://localhost:$PORT/"
echo "公网访问:  通过 frp 映射后的 公网IP:映射端口"
echo "按 Ctrl+C 停止服务"
exec python app.py
