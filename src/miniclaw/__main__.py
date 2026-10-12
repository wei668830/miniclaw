import argparse
import asyncio
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from miniclaw.__version__ import __version__
from miniclaw.constant import EnvVarLoader

load_dotenv()

# 桌面应用后端默认端口
DEFAULT_UI_PORT = 7909


def run_server(args):
    """启动服务器模式"""
    # 使用命令行参数或环境变量
    # 使用 getattr 安全获取属性
    host = getattr(args, 'host', None) or EnvVarLoader.get_str("SERVER_HOST", "0.0.0.0")
    port = getattr(args, 'port', None) or EnvVarLoader.get_int("SERVER_PORT", 8000)
    reload = not getattr(args, 'no_reload', False)  # 默认启用 reload
    log_level = getattr(args, 'log_level', None) or EnvVarLoader.get_str("LOG_LEVEL", "info").lower()

    uvicorn.run(
        "miniclaw.app._app:app",
        host=host,
        port=port,
        reload=reload,
        workers=1,
        log_level=log_level,
    )


def run_cli(args):
    from miniclaw.cli.main import cli_run

    # 可以传递参数给 cli
    if hasattr(args, 'command') and args.command:
        # 如果有命令参数，可以传递
        print(f"执行命令: {args.command}")

    asyncio.run(cli_run())


# ---------------------------------------------------------------------------
# 桌面应用（Electron）启动
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    # src/miniclaw/__main__.py -> 项目根
    return Path(__file__).resolve().parents[2]


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _pick_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _resolve_port(host: str, preferred: int) -> int:
    """优先使用 preferred（默认 7909）；被占用时回退到空闲端口。"""
    return preferred if _port_available(host, preferred) else _pick_free_port(host)


def _wait_healthy(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def _lock_path() -> Path:
    state_dir = Path(EnvVarLoader.get_str("MINICLAW_STATE_DIR", "~/.miniclaw/state")).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "miniclaw-ui.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_single_instance_lock() -> bool:
    """单实例：若已有存活实例则返回 False。"""
    lock = _lock_path()
    if lock.exists():
        try:
            import json

            data = json.loads(lock.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0))
        except Exception:
            pid = 0
        if _pid_alive(pid):
            print(f"检测到 MiniClaw 已在运行（PID={pid}），请勿重复启动。")
            return False
        # 陈旧锁：清理
        try:
            lock.unlink()
        except Exception:
            pass
    import json

    lock.write_text(
        json.dumps({"pid": os.getpid(), "started_at": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


def _release_lock() -> None:
    try:
        _lock_path().unlink()
    except Exception:
        pass


def _electron_cmd(frontend_dir: Path):
    """返回启动 Electron 的命令列表。"""
    bin_dir = frontend_dir / "node_modules" / ".bin"
    exe = bin_dir / ("electron.cmd" if os.name == "nt" else "electron")
    if exe.exists():
        return [str(exe), "."]
    # 回退：使用 npx
    npx = "npx.cmd" if os.name == "nt" else "npx"
    return [npx, "electron", "."]


def run_ui(args):
    """启动桌面应用（后端 + Electron）。"""
    if not _acquire_single_instance_lock():
        return 1

    host = getattr(args, 'host', None) or "127.0.0.1"
    # 桌面应用后端端口固定以 7909 为默认，独立于 `server` 子命令的 SERVER_PORT（.env 中常为 8000）；
    # 可用 --port 或 MINICLAW_UI_PORT 覆盖；被占用时回退空闲端口。
    port = getattr(args, 'port', None) or EnvVarLoader.get_int("MINICLAW_UI_PORT", DEFAULT_UI_PORT)
    port = _resolve_port(host, port)
    token = secrets.token_urlsafe(32)
    dev = getattr(args, 'dev', False)

    backend_proc = None
    electron_proc = None
    try:
        # 1) 启动后端
        if not getattr(args, 'no_backend', False):
            env = {
                **os.environ,
                "MINICLAW_API_TOKEN": token,
                "SERVER_HOST": host,
                "SERVER_PORT": str(port),
                "MINICLAW_PARENT_PID": str(os.getpid()),
                "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
            }
            cmd = [
                sys.executable, "-m", "uvicorn", "miniclaw.app._app:app",
                "--host", host, "--port", str(port),
            ]
            if dev:
                cmd.append("--reload")
            backend_proc = subprocess.Popen(cmd, env=env)
            print(f"后端启动中（{host}:{port}）...")
            if not _wait_healthy(f"http://{host}:{port}/api/health", timeout=30):
                print("后端健康检查超时，请检查依赖与配置。")
                return 1

        # 2) 启动 Electron
        frontend_dir = _project_root() / "frontend"
        if not frontend_dir.exists():
            print(f"未找到前端工程目录: {frontend_dir}（请先创建/构建前端）")
            return 1
        if not getattr(args, 'no_build', False) and not dev and not (frontend_dir / "dist").exists():
            print("前端尚未构建，正在执行 npm run build ...")
            subprocess.run(["npm", "run", "build"], cwd=frontend_dir, check=False)

        electron_env = {
            **os.environ,
            "MINICLAW_BACKEND_URL": f"http://{host}:{port}",
            "MINICLAW_API_TOKEN": token,
            "MINICLAW_DEV": "1" if dev else "0",
        }
        electron_cmd = _electron_cmd(frontend_dir)
        print(f"启动 Electron: {' '.join(electron_cmd)}")
        electron_proc = subprocess.Popen(electron_cmd, cwd=frontend_dir, env=electron_env)

        # 3) 等待 Electron 退出
        electron_proc.wait()
        return 0
    except FileNotFoundError as e:
        print(f"启动失败（缺少依赖）: {e}")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        # UI 关闭 ⇒ 后端同步销毁
        if electron_proc is not None and electron_proc.poll() is None:
            try:
                electron_proc.terminate()
            except Exception:
                pass
        if backend_proc is not None:
            try:
                backend_proc.terminate()
                try:
                    backend_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    backend_proc.kill()
            except Exception:
                pass
        _release_lock()


def create_parser():
    """创建命令行参数解析器（子命令方式）"""
    parser = argparse.ArgumentParser(
        prog='miniclaw',
        description='MiniClaw - 控制台应用'
    )

    # 全局参数
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f"{__version__}",
    )

    # 创建子命令解析器
    subparsers = parser.add_subparsers(
        dest='command',
        title='子命令',
        description='可用命令',
        required=False,
        help='子命令帮助'
    )

    # server 子命令
    server_parser = subparsers.add_parser('server', help='启动服务器模式')
    server_parser.add_argument('--host', help='服务器主机地址')
    server_parser.add_argument('--port', type=int, help='服务器端口')
    server_parser.add_argument('--log-level', choices=['debug', 'info', 'warning', 'error'], help='日志级别')
    server_parser.add_argument('--no-reload', action='store_true', help='禁用自动重载')

    # cli 子命令
    cli_parser = subparsers.add_parser('cli', help='启动 CLI 交互模式')

    # ui 子命令（桌面应用）
    ui_parser = subparsers.add_parser('ui', help='启动桌面应用（Electron）')
    ui_parser.add_argument('--host', default=None, help='后端监听地址（默认 127.0.0.1）')
    ui_parser.add_argument('--port', type=int, default=None, help='后端监听端口（默认 7909）')
    ui_parser.add_argument('--dev', action='store_true', help='开发模式（后端 reload + 前端 devServer）')
    ui_parser.add_argument('--no-backend', action='store_true', help='不启动后端（复用已有后端）')
    ui_parser.add_argument('--no-build', action='store_true', help='跳过前端构建（假定 dist 已存在）')
    ui_parser.add_argument('--log-level', choices=['debug', 'info', 'warning', 'error'], help='日志级别')

    return parser


def main():
    """主入口函数"""
    parser = create_parser()
    args = parser.parse_args()

    # 如果没有指定子命令，默认进入 cli 模式
    if not args.command:
        print("未指定模式，默认进入 CLI 交互模式")
        run_cli(args)
    elif args.command == 'server':
        print("启动服务器模式...")
        run_server(args)
    elif args.command == 'cli':
        print("启动 CLI 交互模式...")
        run_cli(args)
    elif args.command == 'ui':
        print("启动桌面应用...")
        return run_ui(args)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
