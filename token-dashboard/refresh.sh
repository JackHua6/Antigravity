#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[错误] 未检测到 python3，请先安装 Python 3.9+。" >&2
  exit 1
fi

python3 -B refresh_dashboard.py --no-open

if command -v open >/dev/null 2>&1; then
  open "./token_dashboard.html"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "./token_dashboard.html" >/dev/null 2>&1 &
else
  echo "请使用浏览器打开：$(pwd)/token_dashboard.html"
fi
