import pytest

from aiqo_pg_ai_report import pg_aiqo_report


def test_version_flag_shows_version_and_exits(monkeypatch, capsys):
    monkeypatch.setattr(pg_aiqo_report, "get_package_version", lambda: "1.2.3")
    monkeypatch.setattr(pg_aiqo_report, "get_litellm_version", lambda: "9.9.9")

    with pytest.raises(SystemExit) as exc:
        pg_aiqo_report.parse_cli_arguments(["-v"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "1.2.3" in captured.out
    assert "litellm 9.9.9" in captured.out
