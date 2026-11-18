#!/bin/sh
# No secrets are supplied in arguments, shell variables, or persistent files.
set -eu
cd "$(dirname "$0")"
if ! ./start-local-web.command --prompt-api-key --enable-paid-run "$@"; then
  printf '%s\n' '未启动：请先停止本副本旧服务，检查 provider.local.json 或端口。取消输入也会退出。' '按回车关闭。'
  read -r answer
  exit 2
fi
