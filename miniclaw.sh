#!/bin/bash
# 统一启动入口（Linux / macOS / WSL；Windows 原生用 miniclaw.bat）
# 解释器解析优先级：$MINICLAW_PYTHON > 工程内 .venv（uv 管理）> conda 环境 > PATH 上的 python
# 可选子命令：ui（桌面应用，后端 7909 + Electron）、server（仅后端）、cli
ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON=""

# uv 管理的项目虚拟环境（uv sync 创建）：Linux/macOS 为 bin/python，Windows(Git Bash) 为 Scripts/python.exe
if [ -z "$PYTHON" ]; then
    for CAND in "$ROOT/.venv/bin/python" "$ROOT/.venv/Scripts/python.exe"; do
        if [ -x "$CAND" ]; then
            PYTHON="$CAND"
            break
        fi
    done
fi

# 4) 回退到 PATH 上的解释器
if [ -z "$PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    else
        PYTHON=python
    fi
fi

exec "$PYTHON" -m miniclaw "$@"
