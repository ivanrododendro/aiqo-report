import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import json
from datetime import datetime
import re
import base64

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
        self._setup_minification_filters()
        self.template = self.env.get_template("report_template.html")
        self.data_processor = ReportDataProcessor()

    def _setup_custom_filters(self):
        """Setup custom Jinja2 filters for common transformations."""

        def safe_id(text):
            """Convert text to safe HTML ID by replacing non-alphanumeric characters with dashes."""
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

        def embed_image(relative_path):
            """Convert image file to base64 encoded string for embedding."""
            try:
                # Construct full path relative to template base
                templates_path = Path(self.env.loader.searchpath[0])
                image_path = templates_path / relative_path
                
                if not image_path.exists():
                    logger.warning(f"Image not found: {image_path}")
                    return ""
                
                # Read and encode image
                with open(image_path, "rb") as image_file:
                    encoded = base64.b64encode(image_file.read()).decode('utf-8')
                return encoded
            except Exception as e:
                logger.error(f"Error embedding image {relative_path}: {e}")
                return ""

        self.env.filters["safe_id"] = safe_id
        self.env.filters["truncate_code"] = truncate_code
        self.env.filters["format_date"] = format_date
        self.env.filters["embed_image"] = embed_image

    def _setup_minification_filters(self):
        """Setup minification filters for CSS and JS."""
        
        def minify_css(css_content):
            """Simple CSS minification."""
            # Remove comments
            css_content = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)
            # Remove whitespace
            css_content = re.sub(r'\s+', ' ', css_content)
            # Remove spaces around special characters
            css_content = re.sub(r'\s*([{}:;,>+~])\s*', r'\1', css_content)
            return css_content.strip()
        
        def minify_js(js_content):
            """Simple JavaScript minification."""
            # Remove single-line comments (but preserve URLs)
            js_content = re.sub(r'(?<!:)//.*?$', '', js_content, flags=re.MULTILINE)
            # Remove multi-line comments
            js_content = re.sub(r'/\*.*?\*/', '', js_content, flags=re.DOTALL)
            # Remove excessive whitespace (but preserve necessary spaces)
            js_content = re.sub(r'\s+', ' ', js_content)
            # Remove spaces around operators and punctuation
            js_content = re.sub(r'\s*([{}();,:\[\]])\s*', r'\1', js_content)
            return js_content.strip()
        
        self.env.filters["minify_css"] = minify_css
        self.env.filters["minify_js"] = minify_js

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
        # Expose a JS-friendly subset of the context. Include reports.by_day
        # so that client-side components (e.g., QueryDetails) can render
        # PEV2 and per-query charts without inline JS loops.
        context["context_json"] = json.dumps(
            {
                "statistics": context["statistics"],
                "charts": context["charts"],
                "optimizations": context["optimizations"],
                "date_hierarchy": context["date_hierarchy"],
                "reports": {"by_day": context["reports"]["by_day"]},
            }
        )

        html_report = self.template.render(**context)
        Path(output_path).write_text(html_report, encoding="utf-8")
