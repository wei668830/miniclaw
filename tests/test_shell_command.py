"""CLI Shell 命令测试：不访问模型或运行危险命令。"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from miniclaw.agents.base_llm_client import TextBlock, ToolResponse
from miniclaw.cli import commands, main


@pytest.fixture
def cli(monkeypatch):
    instance = main.CommandLineInteraction.__new__(main.CommandLineInteraction)
    instance.messages = [{"role": "user", "content": "unchanged"}]
    monkeypatch.setattr(main.console, "print", Mock())
    return instance


@pytest.mark.parametrize("argument", [None, "", "   "])
def test_shell_requires_command(monkeypatch, cli, argument):
    executor = AsyncMock()
    monkeypatch.setattr(main, "execute_shell_command", executor)
    asyncio.run(cli._cmd_shell(argument))
    executor.assert_not_called()
    assert "用法" in main.console.print.call_args.args[0]


@pytest.mark.parametrize("output", ["[red]literal[/red]", "Command failed with exit code 1.\n[stderr]\nfailure"])
def test_shell_dispatch_and_literal_output(monkeypatch, cli, output):
    executor = AsyncMock(return_value=ToolResponse(content=[TextBlock(text=output)]))
    monkeypatch.setattr(main, "execute_shell_command", executor)
    asyncio.run(cli.command_handler('shell dir "my docs" /b'))
    executor.assert_awaited_once_with('dir "my docs" /b', cwd=Path.cwd())
    main.console.print.assert_called_once_with(output, markup=False, highlight=False)
    assert cli.messages == [{"role": "user", "content": "unchanged"}]


def test_shell_unexpected_error(monkeypatch, cli):
    monkeypatch.setattr(main, "execute_shell_command", AsyncMock(side_effect=RuntimeError("unavailable")))
    asyncio.run(cli._cmd_shell("dir"))
    assert "unavailable" in main.console.print.call_args.args[0]


def test_shell_cancellation_propagates(monkeypatch, cli):
    monkeypatch.setattr(main, "execute_shell_command", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cli._cmd_shell("dir"))


def test_shell_registered():
    assert "/shell" in commands.SLASH_COMMANDS
    assert commands.COMMAND_MAP["shell"].handler == "_cmd_shell"
    assert "/shell dir" in commands.COMMAND_MAP["shell"].example
