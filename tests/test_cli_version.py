import pytest

from aiqo_pg_ai_report import pg_autoexplain_analyzer


def test_version_flag_shows_version_and_exits(monkeypatch, capsys):
    monkeypatch.setattr(pg_autoexplain_analyzer, "get_package_version", lambda: "1.2.3")
    monkeypatch.setattr(pg_autoexplain_analyzer, "get_build_date", lambda: "2026-03-22T12:34:56Z")
    monkeypatch.setattr(pg_autoexplain_analyzer, "get_litellm_version", lambda: "9.9.9")

    with pytest.raises(SystemExit) as exc:
        pg_autoexplain_analyzer.parse_cli_arguments(["-v"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "1.2.3" in captured.out
    assert "build date 2026-03-22T12:34:56Z" in captured.out
    assert "litellm 9.9.9" in captured.out
