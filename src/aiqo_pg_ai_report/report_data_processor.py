import logging
from collections import defaultdict
from datetime import datetime
import json
from math import isfinite
import re

logger = logging.getLogger(__name__)

BYTES_PER_BUFFER_BLOCK = 8192
BUFFER_KEYS_FOR_TOTAL_IO = ("shared_read", "shared_dirtied", "shared_written", "temp_read", "temp_written")
DUPLICATE_QUERY_AI_SKIP_MESSAGE = "AI analysis skipped, same query was already analyzed earlier."
PLAN_COMPARISON_STABLE_THRESHOLD = 0.15
POSTGRES_TIME_UNIT_TO_MS = {
    "us": 0.001,
    "ms": 1.0,
    "s": 1000.0,
    "min": 60_000.0,
    "h": 3_600_000.0,
    "d": 86_400_000.0,
}
POSTGRES_TIME_UNIT_LABELS = {
    "us": ("microsecond", "microseconds"),
    "ms": ("ms", "ms"),
    "s": ("second", "seconds"),
    "min": ("minute", "minutes"),
    "h": ("hour", "hours"),
    "d": ("day", "days"),
}


class ReportDataProcessor:
    """
    Processes and prepares all data for the HTML report.
    Centralizes data transformation logic that was previously in templates.
    """

    def __init__(self):
        self.query_name_limit = 140
        self.all_reports = []
        self.reports_by_day = defaultdict(list)
        self.all_query_stats_dict = {}
        self.daily_query_stats = defaultdict(
            lambda: {"total_queries": 0, "cumulated_time": 0.0, "queries_by_code": defaultdict(float)}
        )

    def create_report_entry(self, log_entry, query_code, ai_hints):
        """
        Crea una entrée de rapport à partir des données de log et des indices AI.
        """
        execution_plan = log_entry["execution_plan"]
        timestamp = log_entry["timestamp"]
        duration = log_entry["duration"]

        def _truncate_title(text: str, limit: int = 180) -> str:
            """Trim title to avoid overly long headings."""
            return text if len(text) <= limit else text[:limit] + "..."

        title = _truncate_title(log_entry.get("title", ""))

        # Validate and sanitize execution plan
        if execution_plan is None or execution_plan == "":
            execution_plan = "No execution plan available"
            seq_scan_indicator = False
        else:
            # Ensure execution_plan is a string for text search
            plan_str = execution_plan if isinstance(execution_plan, str) else str(execution_plan)
            seq_scan_indicator = "Seq Scan" in plan_str

        return {
            "title": title,
            "ai_hints": ai_hints,
            "plan": execution_plan,
            "query_text": log_entry["query_text"],
            "query_timestamp": timestamp,
            "code": query_code,
            "day": timestamp[:10],
            "seq_scan_indicator": seq_scan_indicator,
            "duration": duration,
            "cost": log_entry["cost"],
            "rows": log_entry["rows"],
            "buffers": log_entry.get("buffers"),
            "wal": log_entry.get("wal"),
        }

    def update_statistics(self, report):
        """
        Met à jour toutes les structures de données statistiques avec la nouvelle entrée de rapport.
        """
        self.all_reports.append(report)
        self.reports_by_day[report["day"]].append(report)

        query_code = report["code"]
        duration = report["duration"]
        day = report["day"]

        # Met à jour les statistiques globales
        if query_code not in self.all_query_stats_dict:
            self.all_query_stats_dict[query_code] = {
                "code": query_code,
                "name": report["title"],
                "count": 1,
                "cumulated_time": duration,
            }
        else:
            self.all_query_stats_dict[query_code]["count"] += 1
            self.all_query_stats_dict[query_code]["cumulated_time"] += duration

        # Met à jour les statistiques quotidiennes
        self.daily_query_stats[day]["total_queries"] += 1
        self.daily_query_stats[day]["cumulated_time"] += duration
        self.daily_query_stats[day]["queries_by_code"][query_code] += duration

    def get_query_stats_list(self):
        """
        Retourne la liste des statistiques de requêtes triées par temps cumulé.
        """
        return sorted(self.all_query_stats_dict.values(), key=lambda x: x["cumulated_time"], reverse=True)

    def prepare_report_context(
        self,
        title,
        model,
        app_version,
        query_stats,
        reports_by_day,
        daily_query_stats,
        query_optimizations,
        server_optimizations,
        event_optimizations,
        ddl_context,
        server_config_context,
        project_context,
        skip_ai_analysis,
        general_hints_synthesis,
        execution_options=None,
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

        # Build date hierarchy for year/month/day navigation
        date_hierarchy = self._build_date_hierarchy(all_dates)

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
        self._attach_plan_comparisons(enhanced_reports_by_day)
        self._add_duplicate_ai_analysis_links(enhanced_reports_by_day)

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
                "version": app_version,
                "query_name_limit": self.query_name_limit,
                "auto_explain_log_min_duration": self.extract_auto_explain_log_min_duration(server_config_context),
                "execution_options": execution_options or [],
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
                "project": project_context,
            },
            "ai": {
                "general_hints_synthesis": general_hints_synthesis,
            },
            "charts": {
                "all_dates": all_dates,
                "daily_trends": chart_data["daily_trends"],
                "query_series": chart_data["query_series"],
            },
            "date_hierarchy": date_hierarchy,
        }

        return context

    @classmethod
    def extract_auto_explain_log_min_duration(cls, server_config_context: str | None) -> str | None:
        """Extract and format auto_explain.log_min_duration from CONFIG.txt content."""
        if not server_config_context:
            return None

        setting_pattern = re.compile(
            (
                r"\bauto_explain\.log_min_duration\b\s*(?:=|\bTO\b|\|)\s*['\"]?"
                r"([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z]+)?"
            ),
            re.IGNORECASE,
        )

        for raw_line in server_config_context.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("--"):
                continue

            match = setting_pattern.search(line)
            if not match:
                continue

            raw_value = match.group(1)
            unit = (match.group(2) or "ms").lower()
            return cls._format_auto_explain_log_min_duration(raw_value, unit)

        return None

    @classmethod
    def _format_auto_explain_log_min_duration(cls, raw_value: str, unit: str) -> str:
        try:
            value = float(raw_value)
        except ValueError:
            return f"{raw_value} {unit}".strip()

        if value == -1:
            return "disabled (-1)"
        if value == 0:
            return "all statements (0 ms)"

        if unit not in POSTGRES_TIME_UNIT_TO_MS:
            return f"{cls._format_duration_number(value)} {unit}".strip()

        milliseconds = value * POSTGRES_TIME_UNIT_TO_MS[unit]
        return cls._format_duration_from_ms(milliseconds)

    @classmethod
    def _format_duration_from_ms(cls, milliseconds: float) -> str:
        abs_milliseconds = abs(milliseconds)
        display_units = (
            ("d", 86_400_000.0),
            ("h", 3_600_000.0),
            ("min", 60_000.0),
            ("s", 1000.0),
            ("ms", 1.0),
            ("us", 0.001),
        )

        for unit, unit_ms in display_units:
            if abs_milliseconds >= unit_ms or unit == "us":
                value = milliseconds / unit_ms
                singular, plural = POSTGRES_TIME_UNIT_LABELS[unit]
                label = singular if abs(value) == 1 else plural
                return f"{cls._format_duration_number(value)} {label}"

        return f"{cls._format_duration_number(milliseconds)} ms"

    @staticmethod
    def _format_duration_number(value: float) -> str:
        if isfinite(value) and value.is_integer():
            return str(int(value))
        return f"{value:.3f}".rstrip("0").rstrip(".")

    def _collect_all_dates(self, daily_query_stats, query_optimizations, server_optimizations, event_optimizations):
        """Collect unique dates from query reports only and normalize optimization dates."""

        def _normalize_date(ds):
            try:
                parsed = datetime.strptime(ds.replace(".", "-"), "%Y-%m-%d")
                return parsed.strftime("%Y-%m-%d")
            except Exception:
                logger.warning(f"Unexpected date format encountered: {ds}")
                return ds.replace(".", "-")

        # Normalize optimization dates in-place for consistency
        for opts_dict in (query_optimizations,):
            for q, opts in opts_dict.items():
                for opt in opts:
                    opt["date"] = _normalize_date(opt["date"])
        for opt_list in (server_optimizations, event_optimizations):
            for opt in opt_list:
                opt["date"] = _normalize_date(opt["date"])

        # Build the date range strictly from query statistics (i.e., actual report days)
        normalized_stats = {_normalize_date(day) for day in daily_query_stats.keys()}

        return sorted(normalized_stats)

    def _build_date_hierarchy(self, all_dates):
        """
        Build a hierarchical structure of dates organized by year, month, and day.

        Returns:
            dict: {
                "years": {
                    "2024": {
                        "months": {
                            "01": {
                                "name": "January",
                                "days": ["2024-01-15", "2024-01-16", ...]
                            },
                            ...
                        },
                        "all_days": ["2024-01-15", "2024-01-16", ...]
                    },
                    ...
                },
                "all_years": ["2023", "2024", ...],
                "all_months": ["2024-01", "2024-02", ...],
                "all_days": ["2024-01-15", "2024-01-16", ...]
            }
        """
        month_names = {
            "01": "January",
            "02": "February",
            "03": "March",
            "04": "April",
            "05": "May",
            "06": "June",
            "07": "July",
            "08": "August",
            "09": "September",
            "10": "October",
            "11": "November",
            "12": "December",
        }

        hierarchy = {"years": {}, "all_years": [], "all_months": [], "all_days": all_dates}

        # Group dates by year and month
        for date_str in all_dates:
            try:
                year = date_str[:4]
                month = date_str[5:7]
                year_month = f"{year}-{month}"

                # Initialize year if not exists
                if year not in hierarchy["years"]:
                    hierarchy["years"][year] = {"months": {}, "all_days": []}
                    hierarchy["all_years"].append(year)

                # Initialize month if not exists
                if month not in hierarchy["years"][year]["months"]:
                    hierarchy["years"][year]["months"][month] = {
                        "name": month_names.get(month, month),
                        "year_month": year_month,
                        "days": [],
                    }
                    if year_month not in hierarchy["all_months"]:
                        hierarchy["all_months"].append(year_month)

                # Add day to month and year
                hierarchy["years"][year]["months"][month]["days"].append(date_str)
                hierarchy["years"][year]["all_days"].append(date_str)

            except Exception as e:
                logger.warning(f"Error processing date {date_str} for hierarchy: {e}")

        # Sort everything
        hierarchy["all_years"].sort()
        hierarchy["all_months"].sort()

        for year_data in hierarchy["years"].values():
            year_data["all_days"].sort()
            for month_data in year_data["months"].values():
                month_data["days"].sort()

        return hierarchy

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
        valid_dates = set(all_dates)

        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        counter = 0

        date_range = None
        if all_dates:
            try:
                date_range = (
                    datetime.strptime(all_dates[0], "%Y-%m-%d"),
                    datetime.strptime(all_dates[-1], "%Y-%m-%d"),
                )
            except ValueError:
                logger.warning("Unable to parse log date range for annotations filter")

        def _within_log_range(date_str):
            if not date_range:
                return False
            try:
                current = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Unexpected annotation date format: {date_str}")
                return False
            return date_range[0] <= current <= date_range[1]

        # Process query-specific optimizations
        for query_code, opts in query_optimizations.items():
            for opt in opts:
                if opt["date"] not in valid_dates:
                    continue
                annotation_id = alphabet[counter % len(alphabet)]
                legend_entries["query"].append(
                    {
                        "id": annotation_id,
                        "date": opt["date"],
                        "type": "Query",
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
            if not _within_log_range(opt["date"]):
                continue
            annotation_id = alphabet[counter % len(alphabet)]
            opt["display_id"] = annotation_id
            legend_entries["generic"].append(
                {
                    "id": annotation_id,
                    "date": opt["date"],
                    "type": "Server",
                    "query_code": None,
                    "text": opt["text"],
                }
            )
            annotations["generic"].append(
                {
                    "id": annotation_id,
                    "date": opt["date"],
                    "type": "Server",
                    "border_color": "rgba(13, 110, 253, 0.8)",
                }
            )
            counter += 1

        # Process event optimizations
        for opt in event_optimizations:
            if not _within_log_range(opt["date"]):
                continue
            annotation_id = alphabet[counter % len(alphabet)]
            opt["display_id"] = annotation_id
            legend_entries["generic"].append(
                {
                    "id": annotation_id,
                    "date": opt["date"],
                    "type": "Event",
                    "query_code": None,
                    "text": opt["text"],
                }
            )
            annotations["generic"].append(
                {
                    "id": annotation_id,
                    "date": opt["date"],
                    "type": "Event",
                    "border_color": "rgba(108, 117, 125, 0.8)",
                }
            )
            counter += 1

        return {"annotations": annotations, "legend_entries": legend_entries}

    def _enhance_reports_by_day(self, reports_by_day, query_optimizations, server_optimizations):
        """
        Enhance reports with additional computed properties and flags.
        Also converts query_timestamp strings to UTC timestamps (milliseconds since epoch)
        for consistent parsing on the frontend.
        """
        enhanced = {}
        for day, reports in reports_by_day.items():
            enhanced_reports = []
            for report in reports:
                enhanced_report = dict(report)  # Copy original report

                # Add flags for UI indicators
                # Check if query_optimizations is not empty for the specific query code
                enhanced_report["has_query_optimizations"] = bool(query_optimizations.get(report["code"]))
                enhanced_report["has_ai_hints"] = report.get("ai_hints") and not report["ai_hints"].startswith(
                    "AI analysis skipped"
                )

                # Truncate name for display
                enhanced_report["display_name"] = report["title"][: self.query_name_limit]
                enhanced_report["short_code"] = report["code"][:6]

                # Safe ID for HTML elements (dates are already normalized "YYYY-MM-DD")
                enhanced_report["safe_day"] = day
                enhanced_report["plan_structure"] = self._load_plan_structure(report.get("plan"))

                # Convert query_timestamp to UTC milliseconds
                ts = report.get("query_timestamp")
                if ts:
                    try:
                        from datetime import timezone
                        import re

                        # Clean timezone abbreviations if present
                        clean_ts = re.sub(r"\s+[A-Z]{2,4}$", "", ts.strip())

                        # Try multiple formats
                        parsed = None
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                            try:
                                parsed = datetime.strptime(clean_ts, fmt).replace(tzinfo=timezone.utc)
                                break
                            except Exception:
                                continue

                        if parsed:
                            enhanced_report["query_timestamp_utc"] = int(parsed.timestamp() * 1000)
                        else:
                            logger.warning(f"Could not parse timestamp '{ts}' for report {report.get('code')}")
                            enhanced_report["query_timestamp_utc"] = None
                    except Exception as e:
                        logger.warning(f"Timestamp conversion failed for {report.get('code')}: {e}")
                        enhanced_report["query_timestamp_utc"] = None
                else:
                    enhanced_report["query_timestamp_utc"] = None

                query_end_utc = enhanced_report.get("query_timestamp_utc")
                duration_ms = enhanced_report.get("duration")
                if query_end_utc is not None and isinstance(duration_ms, (int, float)) and duration_ms >= 0:
                    enhanced_report["query_start_utc"] = int(query_end_utc - duration_ms)
                    enhanced_report["query_end_utc"] = int(query_end_utc)
                else:
                    enhanced_report["query_start_utc"] = None
                    enhanced_report["query_end_utc"] = query_end_utc

                buffer_bytes, total_io_bytes = self._compute_buffer_metrics(
                    enhanced_report.get("buffers"), enhanced_report.get("wal")
                )
                enhanced_report["buffers_bytes"] = buffer_bytes
                enhanced_report["total_io_bytes"] = total_io_bytes

                enhanced_reports.append(enhanced_report)

            enhanced[day] = sorted(
                enhanced_reports,
                key=lambda report: (
                    report.get("query_start_utc") is None,
                    report.get("query_start_utc") or 0,
                    report.get("query_end_utc") or 0,
                    report.get("code") or "",
                ),
            )

        return enhanced

    def _index_reports_by_code(self, reports_by_day):
        """Create an index of reports by query code for easier lookup."""
        reports_by_code = defaultdict(list)
        for day, reports in reports_by_day.items():
            for report in reports:
                reports_by_code[report["code"]].append({"day": day, "report": report})
        return dict(reports_by_code)

    def _add_duplicate_ai_analysis_links(self, reports_by_day):
        """Attach a jump target for reports where AI analysis was skipped due to duplicate query code."""
        first_analyzed_query_by_code = {}

        for day in sorted(reports_by_day.keys()):
            for index, report in enumerate(reports_by_day[day]):
                ai_hints = report.get("ai_hints") or ""
                is_duplicate_skip = ai_hints.startswith(DUPLICATE_QUERY_AI_SKIP_MESSAGE)
                query_code = report.get("code")

                if is_duplicate_skip and query_code in first_analyzed_query_by_code:
                    report["duplicate_analysis_target"] = first_analyzed_query_by_code[query_code]
                    continue

                if ai_hints and not is_duplicate_skip and query_code not in first_analyzed_query_by_code:
                    first_analyzed_query_by_code[query_code] = {"day": day, "index": index}

    def _attach_plan_comparisons(self, reports_by_day):
        """Attach an MVP plan comparison against the previous execution of the same query code."""
        previous_execution_by_code = {}

        for day in sorted(reports_by_day.keys()):
            for index, report in enumerate(reports_by_day[day]):
                query_code = report.get("code")
                if not query_code:
                    continue

                previous_execution = previous_execution_by_code.get(query_code)
                if previous_execution:
                    report["plan_comparison"] = self._build_plan_comparison(previous_execution, day, index, report)

                previous_execution_by_code[query_code] = {"day": day, "index": index, "report": report}

    def _build_plan_comparison(self, baseline_execution, current_day, current_index, current_report):
        """Build a lightweight comparison payload for the current report against a previous execution."""
        baseline_report = baseline_execution["report"]
        baseline_day = baseline_execution["day"]
        baseline_index = baseline_execution["index"]

        duration_delta = self._compute_delta(baseline_report.get("duration"), current_report.get("duration"))
        total_io_delta = self._compute_delta(baseline_report.get("total_io_bytes"), current_report.get("total_io_bytes"))
        wal_delta = self._compute_delta(
            self._extract_wal_bytes(baseline_report),
            self._extract_wal_bytes(current_report),
        )
        cost_delta = self._compute_delta(baseline_report.get("cost"), current_report.get("cost"))
        rows_delta = self._compute_delta(baseline_report.get("rows"), current_report.get("rows"))

        baseline_plan = self._load_plan_structure(baseline_report.get("plan"))
        current_plan = self._load_plan_structure(current_report.get("plan"))

        comparison = {
            "baseline": {
                "day": baseline_day,
                "index": baseline_index,
                "title": baseline_report.get("title") or baseline_report.get("code"),
                "timestamp": baseline_report.get("query_timestamp"),
            },
            "current": {
                "day": current_day,
                "index": current_index,
                "timestamp": current_report.get("query_timestamp"),
            },
            "status": self._classify_duration_delta(duration_delta),
            "metrics": [
                self._build_metric_entry("Duration", baseline_report.get("duration"), current_report.get("duration"), "duration"),
                self._build_metric_entry("Cost", baseline_report.get("cost"), current_report.get("cost"), "number"),
                self._build_metric_entry("Rows", baseline_report.get("rows"), current_report.get("rows"), "integer"),
                self._build_metric_entry(
                    "Total I/O",
                    baseline_report.get("total_io_bytes"),
                    current_report.get("total_io_bytes"),
                    "bytes",
                ),
                self._build_metric_entry(
                    "WAL",
                    self._extract_wal_bytes(baseline_report),
                    self._extract_wal_bytes(current_report),
                    "bytes",
                ),
            ],
            "summary": self._build_comparison_summary(duration_delta, total_io_delta),
            "highlights": self._build_comparison_highlights(duration_delta, total_io_delta, wal_delta, cost_delta, rows_delta),
            "structural_changes": [],
            "comparison_scope": "metrics_only",
            "tree": None,
            "tree_summary": None,
        }

        if baseline_plan and current_plan:
            structural_changes, features = self._build_structural_changes(baseline_plan, current_plan)
            comparison["structural_changes"] = structural_changes
            comparison["comparison_scope"] = "metrics_and_structure"
            comparison["tree"] = self._build_plan_tree_diff(baseline_plan, current_plan)
            comparison["tree_summary"] = self._summarize_tree_diff(comparison["tree"])

            estimate_highlight = self._build_misestimation_highlight(features)
            if estimate_highlight:
                comparison["highlights"].append(estimate_highlight)

            if features["plan_shape_changed"] and not comparison["summary"].endswith("."):
                comparison["summary"] += "."
            if features["plan_shape_changed"]:
                comparison["summary"] += " Plan shape changed."
        else:
            comparison["highlights"].append("Structural diff unavailable because one of the plans could not be parsed.")

        return comparison

    def _build_plan_tree_diff(self, baseline_plan, current_plan):
        baseline_root = baseline_plan.get("Plan")
        current_root = current_plan.get("Plan")
        if not isinstance(baseline_root, dict) or not isinstance(current_root, dict):
            return None
        return self._diff_plan_nodes(baseline_root, current_root, "0", depth=0)

    def _diff_plan_nodes(self, baseline_node, current_node, path, depth):
        baseline_snapshot = self._snapshot_plan_node(baseline_node)
        current_snapshot = self._snapshot_plan_node(current_node)
        children = []

        if baseline_node and current_node:
            baseline_node_type = (baseline_snapshot or {}).get("node_type")
            current_node_type = (current_snapshot or {}).get("node_type")
            node_type_changed = baseline_node_type != current_node_type
            node_changes = (
                [f"Node type changed from {baseline_node_type} to {current_node_type}."]
                if node_type_changed
                else []
            )
            children = self._diff_plan_children(
                baseline_node.get("Plans", []) or [],
                current_node.get("Plans", []) or [],
                path,
                depth + 1,
            )
            self_changed = node_type_changed
            has_child_changes = any(child["status"] != "unchanged" for child in children)
            status = "changed" if self_changed or has_child_changes else "unchanged"
            self_status = "changed" if self_changed else "unchanged"
        elif baseline_node:
            node_changes = ["Node removed from the current plan."]
            children = [
                self._diff_plan_nodes(child, None, f"{path}.b{index}", depth + 1)
                for index, child in enumerate(baseline_node.get("Plans", []) or [])
                if isinstance(child, dict)
            ]
            status = "removed"
            self_status = "removed"
        else:
            node_changes = ["Node added in the current plan."]
            children = [
                self._diff_plan_nodes(None, child, f"{path}.c{index}", depth + 1)
                for index, child in enumerate(current_node.get("Plans", []) or [])
                if isinstance(child, dict)
            ]
            status = "added"
            self_status = "added"

        display_title = (
            (current_snapshot or {}).get("title")
            or (baseline_snapshot or {}).get("title")
            or "Unknown node"
        )
        display_subtitle = (
            (current_snapshot or {}).get("subtitle")
            or (baseline_snapshot or {}).get("subtitle")
            or ""
        )

        return {
            "path": path,
            "depth": depth,
            "status": status,
            "self_status": self_status,
            "title": display_title,
            "subtitle": display_subtitle,
            "current_label": (current_snapshot or {}).get("node_type"),
            "baseline_label": (baseline_snapshot or {}).get("node_type"),
            "current_subtree_label": self._summarize_plan_subtree(current_node),
            "baseline_subtree_label": self._summarize_plan_subtree(baseline_node),
            "semantic_annotation": self._build_semantic_annotation(
                status, self_status, baseline_node, current_node, baseline_snapshot, current_snapshot
            ),
            "baseline": baseline_snapshot,
            "current": current_snapshot,
            "changes": node_changes,
            "children": children,
            "is_expanded": depth < 1 or status != "unchanged",
        }

    def _diff_plan_children(self, baseline_children, current_children, parent_path, depth):
        normalized_baseline = [child for child in baseline_children if isinstance(child, dict)]
        normalized_current = [child for child in current_children if isinstance(child, dict)]
        matched_current_indexes = set()
        children = []

        for baseline_index, baseline_child in enumerate(normalized_baseline):
            match_index = self._find_matching_child(baseline_child, normalized_current, matched_current_indexes, baseline_index)
            if match_index is None:
                children.append(self._diff_plan_nodes(baseline_child, None, f"{parent_path}.b{baseline_index}", depth))
                continue

            matched_current_indexes.add(match_index)
            children.append(
                self._diff_plan_nodes(
                    baseline_child,
                    normalized_current[match_index],
                    f"{parent_path}.{baseline_index}",
                    depth,
                )
            )

        for current_index, current_child in enumerate(normalized_current):
            if current_index in matched_current_indexes:
                continue
            children.append(self._diff_plan_nodes(None, current_child, f"{parent_path}.c{current_index}", depth))

        return children

    def _find_matching_child(self, baseline_child, current_children, matched_current_indexes, baseline_index):
        baseline_signature = self._plan_node_signature(baseline_child)

        for current_index, current_child in enumerate(current_children):
            if current_index in matched_current_indexes:
                continue
            if self._plan_node_signature(current_child) == baseline_signature:
                return current_index

        baseline_fallback_signature = self._plan_node_signature(baseline_child, include_index=False)
        for current_index, current_child in enumerate(current_children):
            if current_index in matched_current_indexes:
                continue
            if self._plan_node_signature(current_child, include_index=False) == baseline_fallback_signature:
                return current_index

        if baseline_index < len(current_children) and baseline_index not in matched_current_indexes:
            return baseline_index

        return None

    def _snapshot_plan_node(self, node):
        if not isinstance(node, dict):
            return None

        snapshot = {
            "node_type": node.get("Node Type", "Unknown"),
            "title": self._format_plan_node_title(node),
            "subtitle": self._format_plan_node_subtitle(node),
            "metrics": self._build_plan_node_metrics(node),
        }
        return snapshot

    def _build_plan_node_metrics(self, node):
        metrics = []

        def _append_metric(label, value, value_type):
            formatted = self._format_metric_value(value, value_type)
            if formatted == "N/A":
                return
            metrics.append({"label": label, "value": formatted})

        _append_metric("Actual time", node.get("Actual Total Time"), "duration")
        _append_metric("Actual rows", node.get("Actual Rows"), "integer")
        _append_metric("Plan rows", node.get("Plan Rows"), "integer")
        _append_metric("Cost", node.get("Total Cost"), "number")
        _append_metric("Shared read", node.get("Shared Read Blocks"), "integer")
        _append_metric("Temp written", node.get("Temp Written Blocks"), "integer")

        workers_text = self._format_workers(node)
        if workers_text:
            metrics.append({"label": "Workers", "value": workers_text})

        return metrics

    def _summarize_plan_subtree(self, node, max_depth=2):
        if not isinstance(node, dict):
            return ""

        parts = []
        current_node = node
        traversed_depth = 0

        while isinstance(current_node, dict) and traversed_depth < max_depth:
            parts.append(current_node.get("Node Type", "Unknown"))
            children = [child for child in current_node.get("Plans", []) or [] if isinstance(child, dict)]
            if len(children) != 1:
                break
            current_node = children[0]
            traversed_depth += 1

        summary = " -> ".join(parts)
        if isinstance(node.get("Plans"), list) and node.get("Plans"):
            summary += " subtree"
        return summary

    def _build_semantic_annotation(self, status, self_status, baseline_node, current_node, baseline_snapshot, current_snapshot):
        if status == "added":
            return "added"
        if status == "removed":
            return "removed"
        if status == "unchanged":
            return "same"
        if self_status == "changed":
            baseline_label = (baseline_snapshot or {}).get("title") or (baseline_snapshot or {}).get("node_type") or "Unknown"
            return f"changed, was {baseline_label}"
        if status == "changed":
            return "changed subtree"
        return ""

    def _format_plan_node_title(self, node):
        node_type = node.get("Node Type", "Unknown")
        relation_name = node.get("Relation Name")
        index_name = node.get("Index Name")

        if relation_name and index_name:
            return f"{node_type} on {relation_name} using {index_name}"
        if relation_name:
            return f"{node_type} on {relation_name}"
        if index_name:
            return f"{node_type} using {index_name}"
        return node_type

    def _format_plan_node_subtitle(self, node):
        parts = []
        join_type = node.get("Join Type")
        if join_type:
            parts.append(f"{join_type} join")
        parent_relationship = node.get("Parent Relationship")
        if parent_relationship:
            parts.append(parent_relationship)
        if node.get("Parallel Aware"):
            parts.append("Parallel aware")
        return " | ".join(parts)

    def _build_node_change_list(self, baseline_node, current_node):
        changes = []

        baseline_node_type = baseline_node.get("Node Type")
        current_node_type = current_node.get("Node Type")
        if baseline_node_type != current_node_type:
            changes.append(f"Node type changed from {baseline_node_type} to {current_node_type}.")

        baseline_relation = baseline_node.get("Relation Name")
        current_relation = current_node.get("Relation Name")
        if baseline_relation != current_relation and (baseline_relation or current_relation):
            changes.append(
                f"Relation changed from {baseline_relation or 'N/A'} to {current_relation or 'N/A'}."
            )

        baseline_index = baseline_node.get("Index Name")
        current_index = current_node.get("Index Name")
        if baseline_index != current_index and (baseline_index or current_index):
            changes.append(
                f"Index changed from {baseline_index or 'N/A'} to {current_index or 'N/A'}."
            )

        baseline_join = baseline_node.get("Join Type")
        current_join = current_node.get("Join Type")
        if baseline_join != current_join and (baseline_join or current_join):
            changes.append(
                f"Join type changed from {baseline_join or 'N/A'} to {current_join or 'N/A'}."
            )

        changes.extend(
            filter(
                None,
                [
                    self._describe_metric_change("Actual time", baseline_node.get("Actual Total Time"), current_node.get("Actual Total Time"), "duration", 0.20),
                    self._describe_metric_change("Actual rows", baseline_node.get("Actual Rows"), current_node.get("Actual Rows"), "integer", 0.50),
                    self._describe_metric_change("Plan rows", baseline_node.get("Plan Rows"), current_node.get("Plan Rows"), "integer", 0.50),
                    self._describe_metric_change("Cost", baseline_node.get("Total Cost"), current_node.get("Total Cost"), "number", 0.20),
                    self._describe_metric_change(
                        "Shared read blocks",
                        baseline_node.get("Shared Read Blocks"),
                        current_node.get("Shared Read Blocks"),
                        "integer",
                        0.25,
                    ),
                    self._describe_metric_change(
                        "Temp written blocks",
                        baseline_node.get("Temp Written Blocks"),
                        current_node.get("Temp Written Blocks"),
                        "integer",
                        0.25,
                    ),
                ],
            )
        )

        baseline_workers = self._safe_int(baseline_node.get("Workers Launched") or baseline_node.get("Workers Planned"))
        current_workers = self._safe_int(current_node.get("Workers Launched") or current_node.get("Workers Planned"))
        if baseline_workers != current_workers:
            changes.append(f"Workers changed from {baseline_workers} to {current_workers}.")

        return changes

    def _describe_metric_change(self, label, baseline_value, current_value, value_type, threshold):
        delta = self._compute_delta(baseline_value, current_value)
        if delta["direction"] == "na":
            return None
        if delta["direction"] == "flat":
            return None
        if not self._delta_pct_at_least(delta, threshold):
            return None
        direction_label = "increased" if delta["direction"] == "up" else "decreased"
        return f"{label} {direction_label} ({self._format_delta(delta, value_type)})."

    def _plan_node_signature(self, node, include_index=True):
        if not isinstance(node, dict):
            return None
        signature = [
            node.get("Node Type"),
            node.get("Relation Name"),
            node.get("Join Type"),
        ]
        if include_index:
            signature.append(node.get("Index Name"))
        return tuple(signature)

    def _format_workers(self, node):
        planned = self._safe_int(node.get("Workers Planned"))
        launched = self._safe_int(node.get("Workers Launched"))
        if planned == 0 and launched == 0:
            return ""
        if planned and launched:
            return f"{launched}/{planned}"
        return str(launched or planned)

    def _summarize_tree_diff(self, tree):
        if not tree:
            return None

        counts = {"changed": 0, "added": 0, "removed": 0, "unchanged": 0}

        def _walk(node):
            if not isinstance(node, dict):
                return
            status = node.get("status", "unchanged")
            counts[status] = counts.get(status, 0) + 1
            for child in node.get("children", []) or []:
                _walk(child)

        _walk(tree)
        return {
            "total": sum(counts.values()),
            "changed": counts.get("changed", 0),
            "added": counts.get("added", 0),
            "removed": counts.get("removed", 0),
            "unchanged": counts.get("unchanged", 0),
        }

    def _build_metric_entry(self, label, baseline_value, current_value, value_type):
        delta = self._compute_delta(baseline_value, current_value)
        return {
            "label": label,
            "baseline": self._format_metric_value(baseline_value, value_type),
            "current": self._format_metric_value(current_value, value_type),
            "delta": self._format_delta(delta, value_type),
            "direction": delta["direction"],
        }

    def _build_comparison_summary(self, duration_delta, total_io_delta):
        status = self._classify_duration_delta(duration_delta)
        duration_text = self._format_delta(duration_delta, "duration")

        if status == "regressed":
            return f"Regressed versus previous execution ({duration_text})."
        if status == "improved":
            return f"Improved versus previous execution ({duration_text})."

        io_direction = total_io_delta["direction"]
        if io_direction in {"up", "down"}:
            io_text = self._format_delta(total_io_delta, "bytes")
            return f"Stable runtime, but I/O changed ({io_text})."
        return f"Stable versus previous execution ({duration_text})."

    def _build_comparison_highlights(self, duration_delta, total_io_delta, wal_delta, cost_delta, rows_delta):
        highlights = []

        if duration_delta["direction"] == "up" and self._delta_pct_at_least(duration_delta, 0.25):
            highlights.append("Execution time increased materially compared with the previous execution.")
        elif duration_delta["direction"] == "down" and self._delta_pct_at_least(duration_delta, 0.25):
            highlights.append("Execution time improved materially compared with the previous execution.")

        if total_io_delta["direction"] == "up" and self._delta_pct_at_least(total_io_delta, 0.25):
            highlights.append("Total I/O increased, suggesting more reads, writes, or spill activity.")
        elif total_io_delta["direction"] == "down" and self._delta_pct_at_least(total_io_delta, 0.25):
            highlights.append("Total I/O decreased, suggesting a cheaper execution path.")

        if wal_delta["direction"] == "up" and self._delta_pct_at_least(wal_delta, 0.25):
            highlights.append("WAL volume increased, which may indicate heavier write amplification.")

        if cost_delta["direction"] in {"up", "down"} and self._delta_pct_at_least(cost_delta, 0.20):
            direction_label = "increased" if cost_delta["direction"] == "up" else "decreased"
            highlights.append(f"Planner estimated cost {direction_label} significantly.")

        if rows_delta["direction"] in {"up", "down"} and self._delta_pct_at_least(rows_delta, 0.50):
            highlights.append("Returned row volume changed materially between the two executions.")

        return highlights

    def _build_structural_changes(self, baseline_plan, current_plan):
        baseline_features = self._extract_plan_features(baseline_plan)
        current_features = self._extract_plan_features(current_plan)
        changes = []

        if baseline_features["root_node_type"] != current_features["root_node_type"]:
            changes.append(
                f"Root node changed from {baseline_features['root_node_type']} to {current_features['root_node_type']}."
            )

        changes.extend(self._describe_node_count_delta("Seq Scan", baseline_features, current_features))
        changes.extend(self._describe_node_count_delta("Index Scan", baseline_features, current_features))
        changes.extend(self._describe_node_count_delta("Index Only Scan", baseline_features, current_features))
        changes.extend(self._describe_node_count_delta("Bitmap Heap Scan", baseline_features, current_features))
        changes.extend(self._describe_node_count_delta("Nested Loop", baseline_features, current_features))
        changes.extend(self._describe_node_count_delta("Hash Join", baseline_features, current_features))
        changes.extend(self._describe_node_count_delta("Merge Join", baseline_features, current_features))
        changes.extend(self._describe_node_count_delta("Materialize", baseline_features, current_features))
        changes.extend(self._describe_node_count_delta("Sort", baseline_features, current_features))

        worker_delta = current_features["parallel_workers"] - baseline_features["parallel_workers"]
        if worker_delta > 0:
            changes.append(f"Parallel workers increased from {baseline_features['parallel_workers']} to {current_features['parallel_workers']}.")
        elif worker_delta < 0:
            changes.append(f"Parallel workers decreased from {baseline_features['parallel_workers']} to {current_features['parallel_workers']}.")

        features = {
            "plan_shape_changed": baseline_features["shape_signature"] != current_features["shape_signature"],
            "baseline": baseline_features,
            "current": current_features,
        }
        return changes, features

    def _build_misestimation_highlight(self, features):
        baseline_ratio = features["baseline"]["row_misestimation_ratio"]
        current_ratio = features["current"]["row_misestimation_ratio"]
        if baseline_ratio is None or current_ratio is None:
            return None

        if current_ratio >= baseline_ratio * 2 and current_ratio >= 4:
            return "Row estimate drift worsened on the root plan node."
        if baseline_ratio >= current_ratio * 2 and baseline_ratio >= 4:
            return "Row estimate drift improved on the root plan node."
        return None

    def _extract_plan_features(self, plan_json_obj):
        plan_root = plan_json_obj.get("Plan")
        if not isinstance(plan_root, dict):
            return {
                "root_node_type": "Unknown",
                "shape_signature": (),
                "node_counts": {},
                "parallel_workers": 0,
                "row_misestimation_ratio": None,
            }

        node_counts = defaultdict(int)
        shape_signature = []
        parallel_workers = 0

        def _walk(node):
            nonlocal parallel_workers
            if not isinstance(node, dict):
                return

            node_type = node.get("Node Type", "Unknown")
            node_counts[node_type] += 1
            relation = node.get("Relation Name")
            index_name = node.get("Index Name")
            join_type = node.get("Join Type")
            shape_signature.append((node_type, relation, index_name, join_type))

            workers_planned = node.get("Workers Planned")
            workers_launched = node.get("Workers Launched")
            parallel_workers += self._safe_int(workers_launched)
            if not workers_launched:
                parallel_workers += self._safe_int(workers_planned)

            for child in node.get("Plans", []) or []:
                _walk(child)

        _walk(plan_root)

        return {
            "root_node_type": plan_root.get("Node Type", "Unknown"),
            "shape_signature": tuple(shape_signature),
            "node_counts": dict(node_counts),
            "parallel_workers": parallel_workers,
            "row_misestimation_ratio": self._compute_row_misestimation_ratio(plan_root),
        }

    def _describe_node_count_delta(self, node_type, baseline_features, current_features):
        baseline_count = baseline_features["node_counts"].get(node_type, 0)
        current_count = current_features["node_counts"].get(node_type, 0)
        if baseline_count == current_count:
            return []
        if baseline_count == 0 and current_count > 0:
            return [f"{node_type} introduced ({current_count})."]
        if baseline_count > 0 and current_count == 0:
            return [f"{node_type} removed."]

        direction = "increased" if current_count > baseline_count else "decreased"
        return [f"{node_type} count {direction} from {baseline_count} to {current_count}."]

    def _load_plan_structure(self, plan_value):
        if not plan_value:
            return None

        if isinstance(plan_value, dict):
            return plan_value if isinstance(plan_value.get("Plan"), dict) else None

        if not isinstance(plan_value, str):
            return None

        try:
            parsed = json.loads(plan_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._parse_text_plan(plan_value)

        return parsed if isinstance(parsed, dict) and isinstance(parsed.get("Plan"), dict) else None

    def _parse_text_plan(self, plan_text):
        if not isinstance(plan_text, str):
            return None

        plan_nodes = []
        stack = []
        for raw_line in plan_text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            if line.strip().startswith("Settings:"):
                break

            node_match = re.match(
                r"^(?P<indent>\s*)(?:->\s*)?(?P<descriptor>.+?)\s+\(cost="
                r"(?P<startup>\d+(?:\.\d+)?)\.\.(?P<total>\d+(?:\.\d+)?)\s+rows="
                r"(?P<rows>\d+).*$",
                line,
            )
            if node_match:
                indent = len(node_match.group("indent"))
                descriptor = node_match.group("descriptor").strip()
                node = {
                    "Node Type": self._extract_text_node_type(descriptor),
                    "Plans": [],
                }

                relation_name = self._extract_text_relation_name(descriptor)
                if relation_name:
                    node["Relation Name"] = relation_name

                index_name = self._extract_text_index_name(descriptor)
                if index_name:
                    node["Index Name"] = index_name

                join_type = self._extract_text_join_type(descriptor)
                if join_type:
                    node["Join Type"] = join_type

                startup_cost = self._normalize_number(node_match.group("startup"))
                total_cost = self._normalize_number(node_match.group("total"))
                if startup_cost is not None:
                    node["Startup Cost"] = startup_cost
                if total_cost is not None:
                    node["Total Cost"] = total_cost

                plan_rows_match = re.search(r"\brows=(\d+)", line)
                actual_rows_match = re.search(r"\bactual rows=(\d+)", line)
                actual_time_match = re.search(r"\bactual time=\d+(?:\.\d+)?\.\.(\d+(?:\.\d+)?)", line)

                if plan_rows_match:
                    node["Plan Rows"] = self._safe_int(plan_rows_match.group(1))
                if actual_rows_match:
                    node["Actual Rows"] = self._safe_int(actual_rows_match.group(1))
                if actual_time_match:
                    node["Actual Total Time"] = self._normalize_number(actual_time_match.group(1))

                while stack and stack[-1][0] >= indent:
                    stack.pop()
                if stack:
                    stack[-1][1]["Plans"].append(node)
                else:
                    plan_nodes.append(node)

                stack.append((indent, node))
                continue

            detail_match = re.match(r"^(?P<indent>\s*)(?P<detail>.+)$", line)
            if not detail_match:
                continue

            indent = len(detail_match.group("indent"))
            detail = detail_match.group("detail").strip()
            target_node = None
            for stack_indent, candidate_node in reversed(stack):
                if stack_indent < indent:
                    target_node = candidate_node
                    break
            if target_node is None and stack:
                target_node = stack[-1][1]
            if target_node is None:
                continue

            self._apply_text_plan_detail(target_node, detail)

        if not plan_nodes:
            return None

        return {"Plan": plan_nodes[0]}

    def _apply_text_plan_detail(self, node, detail):
        buffers_match = re.search(
            r"Buffers:\s+shared\s+hit=(\d+)(?:\s+read=(\d+))?(?:\s+dirtied=(\d+))?(?:\s+written=(\d+))?(?:,\s*temp\s+read=(\d+))?(?:\s+written=(\d+))?",
            detail,
        )
        if buffers_match:
            shared_hit, shared_read, shared_dirtied, shared_written, temp_read, temp_written = buffers_match.groups()
            if shared_hit is not None:
                node["Shared Hit Blocks"] = self._safe_int(shared_hit)
            if shared_read is not None:
                node["Shared Read Blocks"] = self._safe_int(shared_read)
            if shared_dirtied is not None:
                node["Shared Dirtied Blocks"] = self._safe_int(shared_dirtied)
            if shared_written is not None:
                node["Shared Written Blocks"] = self._safe_int(shared_written)
            if temp_read is not None:
                node["Temp Read Blocks"] = self._safe_int(temp_read)
            if temp_written is not None:
                node["Temp Written Blocks"] = self._safe_int(temp_written)
            return

        workers_planned_match = re.search(r"Workers Planned:\s*(\d+)", detail)
        if workers_planned_match:
            node["Workers Planned"] = self._safe_int(workers_planned_match.group(1))
            return

        workers_launched_match = re.search(r"Workers Launched:\s*(\d+)", detail)
        if workers_launched_match:
            node["Workers Launched"] = self._safe_int(workers_launched_match.group(1))
            return

    @staticmethod
    def _extract_text_node_type(descriptor):
        normalized = re.sub(r"\s+", " ", descriptor).strip()
        normalized = re.sub(r"\s+using\s+.+?\s+on\s+.+$", "", normalized)
        normalized = re.sub(r"\s+on\s+.+$", "", normalized)
        return normalized

    @staticmethod
    def _extract_text_relation_name(descriptor):
        using_match = re.search(r"\bon\s+([^\s(]+)", descriptor)
        return using_match.group(1) if using_match else None

    @staticmethod
    def _extract_text_index_name(descriptor):
        index_match = re.search(r"\busing\s+([^\s(]+)", descriptor)
        return index_match.group(1) if index_match else None

    @staticmethod
    def _extract_text_join_type(descriptor):
        if " Join" not in descriptor:
            return None
        join_prefix = descriptor.split(" Join", 1)[0]
        known_prefixes = ("Inner", "Left", "Right", "Full", "Semi", "Anti")
        return join_prefix if join_prefix in known_prefixes else None

    def _compute_row_misestimation_ratio(self, plan_root):
        actual_rows = self._normalize_number(plan_root.get("Actual Rows"))
        planned_rows = self._normalize_number(plan_root.get("Plan Rows"))
        if actual_rows is None or planned_rows is None:
            return None

        actual_rows = max(actual_rows, 1)
        planned_rows = max(planned_rows, 1)
        return max(actual_rows / planned_rows, planned_rows / actual_rows)

    def _extract_wal_bytes(self, report):
        return self._normalize_number((report.get("wal") or {}).get("bytes"))

    def _compute_delta(self, baseline_value, current_value):
        baseline = self._normalize_number(baseline_value)
        current = self._normalize_number(current_value)
        if baseline is None or current is None:
            return {"baseline": baseline, "current": current, "absolute": None, "pct": None, "direction": "na"}

        absolute = current - baseline
        pct = None if baseline == 0 else absolute / baseline
        if absolute > 0:
            direction = "up"
        elif absolute < 0:
            direction = "down"
        else:
            direction = "flat"

        return {"baseline": baseline, "current": current, "absolute": absolute, "pct": pct, "direction": direction}

    def _classify_duration_delta(self, delta):
        pct = delta.get("pct")
        if pct is None:
            return "stable"
        if pct >= PLAN_COMPARISON_STABLE_THRESHOLD:
            return "regressed"
        if pct <= -PLAN_COMPARISON_STABLE_THRESHOLD:
            return "improved"
        return "stable"

    def _delta_pct_at_least(self, delta, threshold):
        pct = delta.get("pct")
        return pct is not None and abs(pct) >= threshold

    def _format_metric_value(self, value, value_type):
        number = self._normalize_number(value)
        if number is None:
            return "N/A"
        if value_type == "duration":
            return self._format_duration_ms(number)
        if value_type == "bytes":
            return self._format_bytes(number)
        if value_type == "integer":
            return f"{int(round(number)):,}".replace(",", " ")
        return f"{number:,.2f}".replace(",", " ")

    def _format_delta(self, delta, value_type):
        absolute = delta.get("absolute")
        pct = delta.get("pct")
        if absolute is None:
            return "N/A"
        if absolute == 0:
            return "0"

        sign = "+" if absolute > 0 else "-"
        absolute_value = abs(absolute)

        if value_type == "duration":
            absolute_text = self._format_duration_ms(absolute_value)
        elif value_type == "bytes":
            absolute_text = self._format_bytes(absolute_value)
        elif value_type == "integer":
            absolute_text = f"{int(round(absolute_value)):,}".replace(",", " ")
        else:
            absolute_text = f"{absolute_value:,.2f}".replace(",", " ")

        if pct is None:
            return f"{sign}{absolute_text}"
        return f"{sign}{absolute_text} ({pct:+.1%})"

    def _format_duration_ms(self, value):
        milliseconds = self._normalize_number(value)
        if milliseconds is None:
            return "N/A"

        if milliseconds < 1000:
            return f"{milliseconds:.0f} ms"

        seconds = milliseconds / 1000
        if seconds < 60:
            return f"{seconds:.2f} s"

        minutes = seconds / 60
        if minutes < 60:
            return f"{minutes:.2f} min"

        hours = minutes / 60
        return f"{hours:.2f} h"

    def _format_bytes(self, value):
        size = self._normalize_number(value)
        if size is None:
            return "N/A"

        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"

    @staticmethod
    def _safe_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_number(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return None
        return numeric_value if isfinite(numeric_value) else None

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

    def _compute_buffer_metrics(self, buffers, wal):
        """
        Convert buffer statistics expressed in blocks into bytes and compute total I/O.
        WAL metrics are already expressed in bytes, so they are added as-is.
        """
        buffer_bytes = self._convert_buffers_to_bytes(buffers)
        wal_bytes = self._normalize_number((wal or {}).get("bytes"))

        total_components = []
        if buffer_bytes:
            for key in BUFFER_KEYS_FOR_TOTAL_IO:
                total_components.append(buffer_bytes.get(key))
        total_components.append(wal_bytes)

        total_io_bytes = self._sum_optional(total_components)
        return buffer_bytes, total_io_bytes

    @staticmethod
    def _convert_buffers_to_bytes(buffers):
        if not buffers:
            return None

        converted = {}
        has_value = False
        for key, value in buffers.items():
            converted_value = ReportDataProcessor._blocks_to_bytes(value)
            converted[key] = converted_value
            if converted_value is not None:
                has_value = True

        return converted if has_value else None

    @staticmethod
    def _blocks_to_bytes(value):
        if value is None:
            return None
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            logger.debug(f"Skipping non-numeric buffer value: {value}")
            return None
        return numeric_value * BYTES_PER_BUFFER_BLOCK

    @staticmethod
    def _sum_optional(values):
        total = 0
        has_value = False
        for value in values:
            if value is None:
                continue
            total += value
            has_value = True
        return total if has_value else None

    @staticmethod
    def _normalize_number(value):
        if value is None:
            return None
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            logger.debug(f"Skipping non-numeric WAL value: {value}")
            return None
        return numeric_value
