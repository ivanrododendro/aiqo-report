import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

QUERY_NAME_LIMIT = 140

class ReportGenerator:
    def __init__(self, template_base_path):
        self.env = Environment(
            loader=FileSystemLoader(str(template_base_path)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self.template = self.env.get_template("report_templates/report_template.html")

    def generate_report(self, output_path, title, frequent_hints_analysis, model, query_stats, reports_by_day):
        logger.info(f"Generating HTML report in {output_path}")

        html_report = self.template.render(
            title=title,
            frequent_hints_analysis=frequent_hints_analysis,
            model=model,
            query_stats=query_stats,
            reports_by_day=reports_by_day,
            QUERY_NAME_LIMIT=QUERY_NAME_LIMIT
        )
        Path(output_path).write_text(html_report, encoding="utf-8")

