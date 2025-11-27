import types

import pytest

from aiqo_pg_ai_report import pg_autoexplain_analyzer


@pytest.fixture(autouse=True)
def stub_versions(monkeypatch):
    monkeypatch.setattr(pg_autoexplain_analyzer, "get_package_version", lambda: "x")
    monkeypatch.setattr(pg_autoexplain_analyzer, "get_litellm_version", lambda: "y")


def test_supported_models_success(monkeypatch, capsys):
    fake_litellm = types.SimpleNamespace(
        models=lambda: [
            {"model_name": "gpt-foo", "litellm_provider": "openai"},
            "text-dummy",
        ]
    )
    monkeypatch.setattr(pg_autoexplain_analyzer, "litellm", fake_litellm)

    with pytest.raises(SystemExit) as exc:
        pg_autoexplain_analyzer.parse_cli_arguments(["--supported-models"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Supported models" in out
    assert "- gpt-foo (provider: openai)" in out
    assert "- text-dummy" in out


def test_supported_models_failure(monkeypatch, capsys):
    class ErrLitellm:
        @staticmethod
        def models():
            raise RuntimeError("boom")

    monkeypatch.setattr(pg_autoexplain_analyzer, "litellm", ErrLitellm)

    with pytest.raises(SystemExit) as exc:
        pg_autoexplain_analyzer.parse_cli_arguments(["-sm"])

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Unable to retrieve supported models from litellm." in out
