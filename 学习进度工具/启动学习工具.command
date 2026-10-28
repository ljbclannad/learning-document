#!/bin/zsh
cd -- "${0:A:h}"
if [[ -d '/Applications/研习手记.app' ]]; then
  open '/Applications/研习手记.app'
else
  open '学习进度.app'
fi
if [[ $? -ne 0 ]]; then
  printf '\n启动失败，请先运行 python3 build_native.py 构建原生应用。\n'
  read '?按回车关闭此窗口…'
fi
