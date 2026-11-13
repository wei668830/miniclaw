@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON="

rem 解释器解析优先级：MINICLAW_PYTHON 环境变量 > 工程内 .venv（uv 管理）> miniconda 环境 > PATH 上的 python
rem 1) 显式指定：set MINICLAW_PYTHON=C:\path\to\python.exe
if exist "%MINICLAW_PYTHON%" set "PYTHON=%MINICLAW_PYTHON%"

rem 2) uv 管理的项目虚拟环境（uv sync 创建）
if not defined PYTHON if exist "%ROOT%.venv\Scripts\python.exe" set "PYTHON=%ROOT%.venv\Scripts\python.exe"

rem 3) miniconda 环境中的解释器（未创建 .venv 或需复用 conda 环境时）
if not defined PYTHON (
    set "CONDA_PYTHON=C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe"
    if exist "%CONDA_PYTHON%" set "PYTHON=%CONDA_PYTHON%"
)

rem 4) 回退到 PATH 上的 python，避免展开为空导致
rem 出现 '""' / '..."' 之类的 "不是内部或外部命令" 报错。
if not defined PYTHON set "PYTHON=python"

rem 默认（不带参数）进入 CLI 交互模式
rem 可选子命令：ui（桌面应用，后端 7909 + Electron）、server（仅后端）、cli
"%PYTHON%" -m miniclaw %*
endlocal
