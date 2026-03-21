from pathlib import Path

from aiqo_pg_ai_report.report_generator import ReportGenerator


def test_head_template_embeds_svg_favicon():
    template_base_path = Path(__file__).resolve().parents[1] / "src" / "aiqo_pg_ai_report"
    generator = ReportGenerator(template_base_path, debug=True)

    rendered = generator.env.get_template("_head.html").render(metadata={"title": "Test report"}, context_json="{}")

    assert 'rel="icon"' in rendered
    assert 'rel="shortcut icon"' in rendered
    assert "data:image/svg+xml;base64," in rendered
