"""针对 /llm refresh 的离线验证，不启动 CLI 或调用模型服务。"""

from unittest.mock import Mock

import pytest
from dotenv import load_dotenv

from miniclaw.agents.llm_configurator import LLMConfigurator
from miniclaw.agents import llm_configurator
from miniclaw.cli import commands, main


@pytest.fixture
def interaction(monkeypatch):
    cli = main.CommandLineInteraction.__new__(main.CommandLineInteraction)
    cli.llm_name = "default"
    cli.llms = {"default": {"model": "old"}}
    cli.model = "old"
    cli.base_url = "old-url"
    cli.api_key = "old-key"
    cli.custom_llm_provider = "old-provider"
    cli.messages = [{"role": "user", "content": "keep me"}]
    monkeypatch.setattr(main.console, "print", Mock())
    return cli


def test_refresh_reads_changed_dotenv(tmp_path, monkeypatch, interaction):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_MODEL=new\nLLM_BASE_URL=https://new.example\n"
        "LLM_API_KEY=new-key\nCUSTOM_LLM_PROVIDER=new-provider\n",
        encoding="utf-8",
    )
    for key in ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "CUSTOM_LLM_PROVIDER"):
        monkeypatch.setenv(key, "old")
    loader = Mock(side_effect=lambda **kwargs: load_dotenv(env_file, **kwargs))
    monkeypatch.setattr(llm_configurator, "load_dotenv", loader)

    interaction._cmd_llm("refresh")

    loader.assert_called_once_with(override=True)
    assert interaction.model == "new"
    assert interaction.base_url == "https://new.example"
    assert interaction.api_key == "new-key"
    assert interaction.custom_llm_provider == "new-provider"
    assert interaction.messages == [{"role": "user", "content": "keep me"}]


@pytest.mark.parametrize("active, expected", [("named", "named"), ("removed", "default"), ("temp", "temp")])
def test_refresh_selection(monkeypatch, interaction, active, expected):
    interaction.llm_name = active
    configs = {
        "default": {"model": "default-new", "api_key": "key", "base_url": "url"},
        "named": {"model": "named-new", "api_key": "key", "base_url": "url"},
    }
    monkeypatch.setattr(LLMConfigurator, "refresh_llm_configs_by_group", Mock(return_value=configs))

    interaction._cmd_llm("refresh")

    assert interaction.llms == configs
    assert interaction.llm_name == expected
    assert interaction.model == ("old" if active == "temp" else configs[expected]["model"])
    if active == "temp":
        assert interaction.api_key == "old-key"
        assert interaction.base_url == "old-url"
        assert interaction.custom_llm_provider == "old-provider"
    else:
        assert interaction.custom_llm_provider is None


@pytest.mark.parametrize("result", [{}, RuntimeError("secret-key")])
def test_refresh_failure_preserves_state(monkeypatch, interaction, result):
    loader = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
    monkeypatch.setattr(LLMConfigurator, "refresh_llm_configs_by_group", loader)
    before = interaction.__dict__.copy()

    interaction._cmd_llm("refresh")

    assert interaction.__dict__ == before
    assert "secret-key" not in str(main.console.print.call_args_list)


def test_refresh_rejects_arguments(monkeypatch, interaction):
    loader = Mock()
    monkeypatch.setattr(LLMConfigurator, "refresh_llm_configs_by_group", loader)
    interaction._cmd_llm("refresh unexpected")
    loader.assert_not_called()


def test_existing_llm_commands_and_help(interaction):
    interaction.llms["named"] = {"model": "named", "base_url": "url", "api_key": "key"}
    interaction._cmd_llm("use named")
    assert interaction.model == "named"
    interaction._cmd_llm("set temporary$$$url$$$key$$$provider")
    assert interaction.llm_name == "temp"
    assert interaction.custom_llm_provider == "provider"
    interaction._cmd_llm(None)
    assert any("/llm refresh" in spec.example for spec in commands.COMMAND_SPECS)
