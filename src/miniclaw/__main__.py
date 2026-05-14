import argparse
import asyncio
import os
import sys

import uvicorn
from dotenv import load_dotenv

from miniclaw.__version__ import __version__
from miniclaw.constant import EnvVarLoader

load_dotenv()

def run_server(args):
    """启动服务器模式"""
    # 使用命令行参数或环境变量
    host = args.host or os.getenv("SERVER_HOST", "0.0.0.0")
    port = args.port or int(os.getenv("SERVER_PORT", 8000))
    reload = not args.no_reload if hasattr(args, 'no_reload') else True
    log_level = args.log_level or os.getenv("LOG_LEVEL", "info").lower()

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
    else:
        parser.print_help()
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())