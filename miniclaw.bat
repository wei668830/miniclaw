@echo off
setlocal
set "PYTHON=C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe"

rem 默认（不带参数）进入 CLI 交互模式
rem 可选子命令：ui（桌面应用，后端 7909 + Electron）、server（仅后端）、cli
"%PYTHON%" -m miniclaw %*
endlocal
