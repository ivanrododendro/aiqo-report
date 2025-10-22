import logging
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class ReportDataProcessor:
    """
    Processes and prepares all data for the HTML report.
    Centralizes data transformation logic that was previously in templates.
    """

    def __init__(self):
        self.query_name_limit = 140

    def prepare_report_context(
        self,
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
        """
        Prepares a complete, structured context object for the report template.
        All complex calculations and data transformations happen here.
        """
        logger.info("Preparing report context data")

        # Collect all unique dates
        all_dates = self._collect_all_dates(
            daily_query_stats, query_optimizations, server_optimizations, event_optimizations
        )

        # Prepare chart data
        chart_data = self._prepare_chart_data(query_stats, daily_query_stats, all_dates)

        # Prepare optimization annotations
        optimization_annotations = self._prepare_optimization_annotations(
            query_optimizations, server_optimizations, event_optimizations, all_dates
        )

        # Prepare reports with pre-calculated data
        enhanced_reports_by_day = self._enhance_reports_by_day(
            reports_by_day, query_optimizations, server_optimizations
        )

        # Prepare reports indexed by code for easier lookup
        reports_by_code = self._index_reports_by_code(reports_by_day)

        # Convert daily_query_stats to serializable format
        serializable_daily_stats = self._make_daily_stats_serializable(daily_query_stats)

        context = {
            "metadata": {
                "title": title,
                "model": model,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "skip_ai_analysis": skip_ai_analysis,
                "query_name_limit": self.query_name_limit,
            },
            "statistics": {
                "global_query_stats": query_stats,
                "daily_stats": serializable_daily_stats,
            },
            "reports": {
                "by_day": enhanced_reports_by_day,
                "by_code": reports_by_code,
            },
            "optimizations": {
                "query": query_optimizations,
                "server": server_optimizations,
                "event": event_optimizations,
                "annotations": optimization_annotations,
            },
            "contexts": {
                "ddl": ddl_context,
                "server_config": server_config_context,
                "infra": infra_context,
            },
            "charts": {
                "all_dates": all_dates,
                "daily_trends": chart_data["daily_trends"],
                "query_series": chart_data["query_series"],
            },
        }

        return context

    def _collect_all_dates(self, daily_query_stats, query_optimizations, server_optimizations, event_optimizations):
        """Collect all unique dates from various sources and return sorted list."""
        all_dates_set = set()

        # From daily stats
        all_dates_set.update(daily_query_stats.keys())

        # From query optimizations
        for query_code, opts in query_optimizations.items():
            for opt in opts:
                all_dates_set.add(opt["date"])

        # From server optimizations
        for opt in server_optimizations:
            all_dates_set.add(opt["date"])

        # From event optimizations
        for opt in event_optimizations:
            all_dates_set.add(opt["date"])

        return sorted(list(all_dates_set))

    def _prepare_chart_data(self, query_stats, daily_query_stats, all_dates):
        """Prepare data structures optimized for Chart.js rendering."""
        # Prepare query series data
        query_series = []
        for stat in query_stats:
            series_data = []
            for day in all_dates:
                day_stats = daily_query_stats.get(day, {})
                queries_by_code = day_stats.get("queries_by_code", {})
                duration_ms = queries_by_code.get(stat["code"])
                # Convert to minutes or null
                series_data.append(duration_ms / 60000 if duration_ms is not None else None)

            query_series.append(
                {
                    "code": stat["code"],
                    "name": stat["name"],
                    "label": f"[{stat['code'][:6]}] {stat['name'][:self.query_name_limit]}",
                    "data": series_data,
                }
            )

        # Prepare daily trends data
        cumulated_time_data = []
        total_queries_data = []
        for day in all_dates:
            day_stats = daily_query_stats.get(day, {})
            cumulated_time = day_stats.get("cumulated_time")
            total_queries = day_stats.get("total_queries")

            cumulated_time_data.append(cumulated_time / 60000 if cumulated_time is not None else None)
            total_queries_data.append(total_queries if total_queries is not None else None)

        daily_trends = {
            "labels": all_dates,
            "cumulated_time": cumulated_time_data,
            "total_queries": total_queries_data,
        }

        return {"query_series": query_series, "daily_trends": daily_trends}

    def _prepare_optimization_annotations(
        self, query_optimizations, server_optimizations, event_optimizations, all_dates
    ):
        """
        Prepare optimization annotations for charts.
        Returns structured data ready for Chart.js annotation plugin.
        """
        annotations = {
            "query": [],  # For individual query charts
            "generic": [],  # For cumulated time chart (server + event)
        }

        legend_entries = {"query": [], "generic": []}

        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        counter = 0

        # Process query-specific optimizations
        for query_code, opts in query_optimizations.items():
            for opt in opts:
                annotation_id = alphabet[counter % len(alphabet)]
                legend_entries["query"].append(
                    {
                        "id": annotation_id,
                        "date": opt["date"],
                        "type": "Requête",
                        "query_code": query_code,
                        "text": opt["text"],
                    }
                )
                annotations["query"].append(
                    {
                        "id": annotation_id,
                        "date": opt["date"],
                        "query_code": query_code,
                        "border_color": "rgba(255, 0, 0, 0.8)",
                    }
                )
                counter += 1

        # Process server optimizations
        for opt in server_optimizations:
            annotation_id = alphabet[counter % len(alphabet)]
            legend_entries["generic"].append(
                {
                    "id": annotation_id,
                    "date": opt["date"],
                    "type": "Serveur",
                    "query_code": None,
                    "text": opt["text"],
                }
            )
            annotations["generic"].append(
                {"id": annotation_id, "date": opt["date"], "border_color": "rgba(0, 0, 255, 0.8)"}
            )
            counter += 1

        # Process event optimizations
        for opt in event_optimizations:
            annotation_id = alphabet[counter % len(alphabet)]
            legend_entries["generic"].append(
                {
                    "id": annotation_id,
                    "date": opt["date"],
                    "type": "Événement",
                    "query_code": None,
                    "text": opt["text"],
                }
            )
            annotations["generic"].append(
                {"id": annotation_id, "date": opt["date"], "border_color": "rgba(0, 128, 0, 0.8)"}
            )
            counter += 1

        return {"annotations": annotations, "legend_entries": legend_entries}

    def _enhance_reports_by_day(self, reports_by_day, query_optimizations, server_optimizations):
        """
        Enhance reports with additional computed properties and flags.
        """
        enhanced = {}
        for day, reports in reports_by_day.items():
            enhanced_reports = []
            for report in reports:
                enhanced_report = dict(report)  # Copy original report

                # Add flags for UI indicators
                # Check if query_optimizations is not empty for the specific query code
                enhanced_report["has_query_optimizations"] = bool(query_optimizations.get(report["code"]))
                enhanced_report["has_ai_hints"] = (
                    report.get("ai_hints")
                    and not report["ai_hints"].startswith("AI analysis skipped")
                )

                # Truncate name for display
                enhanced_report["display_name"] = report["title"][: self.query_name_limit]
                enhanced_report["short_code"] = report["code"][:6]

                # Safe ID for HTML elements
                enhanced_report["safe_day"] = day.replace(".", "-")

                enhanced_reports.append(enhanced_report)

            enhanced[day] = enhanced_reports

        return enhanced

    def _index_reports_by_code(self, reports_by_day):
        """Create an index of reports by query code for easier lookup."""
        reports_by_code = defaultdict(list)
        for day, reports in reports_by_day.items():
            for report in reports:
                reports_by_code[report["code"]].append({"day": day, "report": report})
        return dict(reports_by_code)

    def _make_daily_stats_serializable(self, daily_query_stats):
        """Convert defaultdicts to regular dicts for JSON serialization."""
        serializable = {}
        for day, data in daily_query_stats.items():
            serializable[day] = {
                "total_queries": data["total_queries"],
                "cumulated_time": data["cumulated_time"],
                "queries_by_code": dict(data["queries_by_code"]),
            }
        return serializable
