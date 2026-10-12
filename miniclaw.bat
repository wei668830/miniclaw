@echo off
setlocal
set "PYTHON=C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe"

rem 若指定解释器不存在，则回退到 PATH 上的 python，避免展开为空导致
rem 出现 '""' / '..."' 之类的 “不是内部或外部命令” 报错。
if not exist "%PYTHON%" set "PYTHON=python"

rem 默认（不带参数）进入 CLI 交互模式
rem 可选子命令：ui（桌面应用，后端 7909 + Electron）、server（仅后端）、cli
"%PYTHON%" -m miniclaw %*
endlocal
