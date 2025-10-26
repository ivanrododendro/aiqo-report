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

        # Validate and sanitize execution plan
        if execution_plan is None or execution_plan == "":
            execution_plan = "No execution plan available"
            seq_scan_indicator = False
        else:
            # Ensure execution_plan is a string for text search
            plan_str = execution_plan if isinstance(execution_plan, str) else str(execution_plan)
            seq_scan_indicator = "Seq Scan" in plan_str

        return {
            "title": job_name + " " + query_name,
            "chatgpt_hints": ai_hints,
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
            "rows": log_entry["rows"]
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
            "date_hierarchy": date_hierarchy,
        }

        return context

    def _collect_all_dates(self, daily_query_stats, query_optimizations, server_optimizations, event_optimizations):
        """Collect all unique dates from various sources and return sorted list."""
        all_dates_set = set()

        # From daily stats
        dates_from_stats = set(daily_query_stats.keys())
        logger.info(f"Dates from daily_query_stats: {sorted(dates_from_stats)}")
        all_dates_set.update(dates_from_stats)

        # From query optimizations
        dates_from_query_opts = set()
        for query_code, opts in query_optimizations.items():
            for opt in opts:
                dates_from_query_opts.add(opt["date"])
        logger.info(f"Dates from query_optimizations: {sorted(dates_from_query_opts)}")
        all_dates_set.update(dates_from_query_opts)

        # From server optimizations
        dates_from_server_opts = {opt["date"] for opt in server_optimizations}
        logger.info(f"Dates from server_optimizations: {sorted(dates_from_server_opts)}")
        all_dates_set.update(dates_from_server_opts)

        # From event optimizations
        dates_from_event_opts = {opt["date"] for opt in event_optimizations}
        logger.info(f"Dates from event_optimizations: {sorted(dates_from_event_opts)}")
        all_dates_set.update(dates_from_event_opts)

        # Normalize all collected dates to "YYYY-MM-DD" and replace in optimizations too
        normalized = set()

        def _normalize_date(ds):
            try:
                parsed = datetime.strptime(ds.replace(".", "-"), "%Y-%m-%d")
                return parsed.strftime("%Y-%m-%d")
            except Exception:
                logger.warning(f"Unexpected date format encountered: {ds}")
                return ds.replace(".", "-")

        for d in all_dates_set:
            normalized.add(_normalize_date(d))

        # Filter out unwanted placeholder dates (1 gennaio)
        unwanted_dates = {'2024-01-01', '2025-01-01'}
        filtered_dates = {d for d in normalized if d not in unwanted_dates}
        
        if unwanted_dates & normalized:
            logger.warning(f"Filtered out placeholder dates: {sorted(unwanted_dates & normalized)}")

        # update opt["date"] everywhere to normalized version
        for opts_dict in (query_optimizations,):
            for q, opts in opts_dict.items():
                for opt in opts:
                    opt["date"] = _normalize_date(opt["date"])
        for opt_list in (server_optimizations, event_optimizations):
            for opt in opt_list:
                opt["date"] = _normalize_date(opt["date"])

        return sorted(list(filtered_dates))

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
                    report.get("chatgpt_hints")
                    and not report["chatgpt_hints"].startswith("AI analysis skipped")
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
