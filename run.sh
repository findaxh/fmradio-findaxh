#!/usr/bin/env bash
# FM 网络电台 - Ubuntu / Linux 启动脚本（后台守护 + 开机自启）
#
# 不创建任何虚拟环境：直接使用「已存在的 Python 环境」。
#   默认：/home/japp/miniconda3/envs/pyServer/bin/python（见下方 DEFAULT_PY）
#   覆盖：PYTHON=/path/to/python ./run.sh start
#
# 用法:
#   ./run.sh              后台启动（默认，可关闭终端）
#   ./run.sh start        后台启动
#   ./run.sh stop         停止
#   ./run.sh restart      重启
#   ./run.sh status       查看运行状态
#   ./run.sh logs         实时查看日志（Ctrl+C 只退出查看，不停止服务）
#   ./run.sh run          前台运行（调试用，Ctrl+C 即停）
#   ./run.sh enable       设置开机自启（systemd）
#   ./run.sh disable      取消开机自启
#
# 环境变量: PORT（默认 6123）、PYTHON（覆盖解释器）
set -euo pipefail
cd "$(dirname "$0")"

APP_DIR="$(pwd)"
DEFAULT_PY="/home/japp/miniconda3/envs/pyServer/bin/python"
SERVICE_NAME="fmradio"
PID_FILE="$APP_DIR/.fmradio.pid"
LOG_FILE="$APP_DIR/fmradio.log"

export PORT="${PORT:-6123}"

# 强制直连：不使用任何系统/环境代理
export RB_PROXY_MODE="${RB_PROXY_MODE:-direct}"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

# ---- 选择 Python 解释器：显式指定 > 默认环境 > python3 > python ----
if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x "$DEFAULT_PY" ]; then
  PY="$DEFAULT_PY"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
  echo "警告：默认环境 $DEFAULT_PY 不存在，回退到 $PY"
elif command -v python >/dev/null 2>&1; then
  PY="$(command -v python)"
  echo "警告：默认环境 $DEFAULT_PY 不存在，回退到 $PY"
else
  echo "错误：未找到可用的 Python。"
  echo "  默认环境 $DEFAULT_PY 不存在，且未找到 python3 / python。"
  echo "  请用 PYTHON=/path/to/python ./run.sh start 指定解释器。"
  exit 1
fi

if [ ! -x "$PY" ] && ! command -v "$PY" >/dev/null 2>&1; then
  echo "错误：指定的 Python 解释器不可用: $PY"
  exit 1
fi

check_deps() {
  if "$PY" -c 'import flask, requests' >/dev/null 2>&1; then
    return 0
  fi
  echo "缺少依赖，安装到当前环境: $PY -m pip install -r requirements.txt"
  if ! "$PY" -m pip install -q -r requirements.txt; then
    echo "常规安装失败，重试 --break-system-packages ..."
    if ! "$PY" -m pip install -q --break-system-packages -r requirements.txt; then
      echo "错误：依赖安装失败。请手动执行："
      echo "  $PY -m pip install -r requirements.txt"
      exit 1
    fi
  fi
}

is_running() {
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

current_pid() { cat "$PID_FILE" 2>/dev/null || true; }

do_start() {
  if is_running; then
    echo "服务已在运行，PID=$(current_pid)，访问 http://localhost:$PORT/"
    return 0
  fi
  echo "Python 环境: $PY ($("$PY" -c 'import sys;print(sys.version.split()[0])'))"
  if [ -n "${CONDA_DEFAULT_ENV:-}" ]; then echo "Conda 环境: $CONDA_DEFAULT_ENV"; fi
  check_deps
  echo "后台启动中...（日志文件: $LOG_FILE）"
  nohup "$PY" app.py >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 1
  if is_running; then
    echo
    echo "已启动  PID=$(current_pid)  端口=$PORT"
    echo "本地访问:  http://localhost:$PORT/"
    echo "公网访问:  通过 frp 映射后的 公网IP:映射端口（可选，本地使用无需配置）"
    echo "现在可以关闭终端，服务继续在后台运行。"
  else
    echo "启动失败，请查看日志: $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
  fi
}

do_stop() {
  if ! is_running; then
    echo "服务未在运行。"
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid="$(current_pid)"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.3
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "未响应，强制结束 PID=$pid"
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "已停止。"
}

do_status() {
  if is_running; then
    echo "运行中:  PID=$(current_pid)  端口=$PORT  http://localhost:$PORT/"
  elif command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "由 systemd 管理并运行中（./run.sh disable 可取消开机自启）"
    systemctl status "$SERVICE_NAME" --no-pager | head -n 5
  else
    echo "未运行。"
  fi
}

do_logs() {
  [ -f "$LOG_FILE" ] || touch "$LOG_FILE"
  echo "实时日志: $LOG_FILE （Ctrl+C 只退出查看，不会停止服务）"
  tail -n 50 -f "$LOG_FILE"
}

do_run() {
  echo "前台运行（调试模式，Ctrl+C 停止）"
  echo "  解释器: $PY"
  echo "  端口:   $PORT"
  check_deps
  exec "$PY" app.py
}

do_enable() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "错误：未找到 systemd，无法设置开机自启。"
    echo "可改为把下面一行加入 crontab（crontab -e）："
    echo "  @reboot cd $APP_DIR && PORT=$PORT $PY app.py >> $LOG_FILE 2>&1"
    exit 1
  fi
  if ! command -v sudo >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ]; then
    echo "错误：需要 sudo 或 root 权限来安装 systemd 服务。"
    exit 1
  fi
  local tmp
  tmp="$(mktemp)"
  cat >"$tmp" <<EOF
[Unit]
Description=FM Radio Web Service
After=network.target

[Service]
Type=simple
User=${SUDO_USER:-$(id -un)}
WorkingDirectory=$APP_DIR
Environment=PORT=$PORT
Environment=RB_PROXY_MODE=direct
Environment=HTTP_PROXY=
Environment=HTTPS_PROXY=
ExecStart=$PY app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  sudo mv "$tmp" "/etc/systemd/system/$SERVICE_NAME.service"
  sudo chmod 644 "/etc/systemd/system/$SERVICE_NAME.service"
  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_NAME"
  sudo systemctl restart "$SERVICE_NAME"
  echo
  echo "已设置开机自启并启动服务。"
  sudo systemctl status "$SERVICE_NAME" --no-pager | head -n 8
}

do_disable() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "错误：未找到 systemd。"
    exit 1
  fi
  sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  sudo rm -f "/etc/systemd/system/$SERVICE_NAME.service"
  sudo systemctl daemon-reload
  echo "已取消开机自启并停止服务。"
}

usage() {
  cat <<'USAGE'
用法: ./run.sh <命令>

  (无参数)     后台启动（默认，可关闭终端）
  start        后台启动
  stop         停止
  restart      重启
  status       查看运行状态
  logs         实时查看日志（Ctrl+C 只退出查看，不停止服务）
  run          前台运行（调试用，Ctrl+C 即停）
  enable       设置开机自启（systemd）
  disable      取消开机自启
  help         显示本帮助

环境变量: PORT（默认 6123）、PYTHON（覆盖默认解释器）
默认环境: /home/japp/miniconda3/envs/pyServer/bin/python
USAGE
}

case "${1:-start}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; do_start ;;
  status)  do_status ;;
  logs)    do_logs ;;
  run)     do_run ;;
  enable)  do_enable ;;
  disable) do_disable ;;
  -h|--help|help) usage ;;
  *)
    echo "未知命令: $1"
    usage
    exit 1
    ;;
esac
