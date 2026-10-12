#!/bin/bash
# 默认（不带参数）进入 CLI 交互模式
# 可选子命令：ui（桌面应用，后端 7909 + Electron）、server（仅后端）、cli
PYTHON=/your/path/python

"$PYTHON" -m miniclaw "$@"
