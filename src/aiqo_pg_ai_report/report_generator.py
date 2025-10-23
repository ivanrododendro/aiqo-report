import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import json
from datetime import datetime

from .report_data_processor import ReportDataProcessor

logger = logging.getLogger(__name__)

QUERY_NAME_LIMIT = 140


class ReportGenerator:
    def __init__(self, template_base_path):
        # Ensure correct templates folder for Jinja loader
        templates_path = Path(template_base_path) / "report_templates"
        self.env = Environment(
            loader=FileSystemLoader(str(templates_path)),
            autoescape=select_autoescape(["html", "xml"])
        )
        self._setup_custom_filters()
        self.template = self.env.get_template("report_template.html")
        self.data_processor = ReportDataProcessor()

    def _setup_custom_filters(self):
        """Setup custom Jinja2 filters for common transformations."""

        def safe_id(text):
            """Convert text to safe HTML ID by replacing non-alphanumeric characters with dashes."""
            import re
            if not text:
                return ""
            # Replace any non-alphanumeric characters with hyphens
            return re.sub(r'[^a-zA-Z0-9]', '-', str(text))

        def truncate_code(code, length=6):
            """Truncate query code to specified length."""
            return code[:length] if code else ""

        def format_date(date_str):
            """Format date string for display."""
            return date_str

        self.env.filters["safe_id"] = safe_id
        self.env.filters["truncate_code"] = truncate_code
        self.env.filters["format_date"] = format_date

    def generate_report(
        self,
        output_path,
        title,
        model,
        query_stats,
        reports_by_day,
        daily_query_stats,
        query_optimizations,
        server_optimizations,
        event_optimizations,
        ddl_context,
        server_config_context,
        infra_context,
        skip_ai_analysis,
    ):
        logger.info(f"Generating HTML report in {output_path}")

        # Use data processor to prepare all context data
        context = self.data_processor.prepare_report_context(
            title=title,
            model=model,
            query_stats=query_stats,
            reports_by_day=reports_by_day,
            daily_query_stats=daily_query_stats,
            query_optimizations=query_optimizations,
            server_optimizations=server_optimizations,
            event_optimizations=event_optimizations,
            ddl_context=ddl_context,
            server_config_context=server_config_context,
            infra_context=infra_context,
            skip_ai_analysis=skip_ai_analysis,
        )

        # Serialize context for JavaScript
        context["context_json"] = json.dumps(
            {
                "statistics": context["statistics"],
                "charts": context["charts"],
                "optimizations": context["optimizations"],
            }
        )

        html_report = self.template.render(**context)
        Path(output_path).write_text(html_report, encoding="utf-8")
