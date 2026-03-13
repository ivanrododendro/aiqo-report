import logging
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

BYTES_PER_BUFFER_BLOCK = 8192
BUFFER_KEYS_FOR_TOTAL_IO = ("shared_read", "shared_dirtied", "shared_written", "temp_read", "temp_written")
DUPLICATE_QUERY_AI_SKIP_MESSAGE = "AI analysis skipped, same query was already analyzed earlier."


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
        query_name = log_entry["query_name"]
        job_name = log_entry["job_name"]
        execution_plan = log_entry["execution_plan"]
        timestamp = log_entry["timestamp"]
        duration = log_entry["duration"]

        def _truncate_title(text: str, limit: int = 180) -> str:
            """Trim title to avoid overly long headings."""
            return text if len(text) <= limit else text[:limit] + "..."

        title = _truncate_title(log_entry.get("title", (job_name + " " + query_name).strip()))

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
            "query_name": query_name,
            "job_name": job_name,
            "code": query_code,
            "day": timestamp[:10],
            "seq_scan_indicator": seq_scan_indicator,
            "duration": duration,
            "cost": log_entry["cost"],
            "rows": log_entry["rows"],
            "buffers": log_entry.get("buffers"),
            "wal": log_entry.get("wal")
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
                "name": report["query_name"],
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
            "charts": {
                "all_dates": all_dates,
                "daily_trends": chart_data["daily_trends"],
                "query_series": chart_data["query_series"],
            },
            "date_hierarchy": date_hierarchy,
        }

        return context

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
            "01": "January", "02": "February", "03": "March", "04": "April",
            "05": "May", "06": "June", "07": "July", "08": "August",
            "09": "September", "10": "October", "11": "November", "12": "December"
        }
        
        hierarchy = {
            "years": {},
            "all_years": [],
            "all_months": [],
            "all_days": all_dates
        }
        
        # Group dates by year and month
        for date_str in all_dates:
            try:
                year = date_str[:4]
                month = date_str[5:7]
                year_month = f"{year}-{month}"
                
                # Initialize year if not exists
                if year not in hierarchy["years"]:
                    hierarchy["years"][year] = {
                        "months": {},
                        "all_days": []
                    }
                    hierarchy["all_years"].append(year)
                
                # Initialize month if not exists
                if month not in hierarchy["years"][year]["months"]:
                    hierarchy["years"][year]["months"][month] = {
                        "name": month_names.get(month, month),
                        "year_month": year_month,
                        "days": []
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
                enhanced_report["has_ai_hints"] = (
                    report.get("ai_hints")
                    and not report["ai_hints"].startswith("AI analysis skipped")
                )

                # Truncate name for display
                enhanced_report["display_name"] = report["title"][: self.query_name_limit]
                enhanced_report["short_code"] = report["code"][:6]

                # Safe ID for HTML elements (dates are already normalized "YYYY-MM-DD")
                enhanced_report["safe_day"] = day

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
