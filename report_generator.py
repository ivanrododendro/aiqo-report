import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import json # Import json to dump the daily_query_stats

logger = logging.getLogger(__name__)

QUERY_NAME_LIMIT = 140

class ReportGenerator:
    def __init__(self, template_base_path):
        self.env = Environment(
            loader=FileSystemLoader(str(template_base_path)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self.template = self.env.get_template("report_templates/report_template.html")

    def generate_report(self, output_path, title, model, query_stats, reports_by_day, daily_query_stats, query_optimizations): # Ajout de query_optimizations
        logger.info(f"Generating HTML report in {output_path}")

        # Convert defaultdicts to regular dicts for JSON serialization
        # Also convert inner defaultdicts
        serializable_daily_query_stats = {}
        for day, data in daily_query_stats.items():
            serializable_daily_query_stats[day] = {
                "total_queries": data["total_queries"],
                "cumulated_time": data["cumulated_time"],
                "queries_by_code": dict(data["queries_by_code"]) # Convert inner defaultdict to dict
            }

        html_report = self.template.render(
            title=title,
            model=model,
            query_stats=query_stats,
            reports_by_day=reports_by_day,
            QUERY_NAME_LIMIT=QUERY_NAME_LIMIT,
            daily_query_stats_json=json.dumps(serializable_daily_query_stats), # Pass as JSON string
            query_optimizations=query_optimizations # Nouveau paramètre passé au template
        )
        Path(output_path).write_text(html_report, encoding="utf-8")

