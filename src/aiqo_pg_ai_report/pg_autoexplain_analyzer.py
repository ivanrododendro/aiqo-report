#!/usr/bin/env python

import argparse
import logging
import sys  # Import sys for exit
from collections import defaultdict
from pathlib import Path

# Ensure package imports resolve when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import classes and necessary constants from their new modules
from aiqo_pg_ai_report.ai_caller import AiCaller, DEFAULT_AI_CALL_TIMEOUT
from aiqo_pg_ai_report.log_parser import JsonLogParser, TextLogParser
from aiqo_pg_ai_report.report_generator import ReportGenerator
from aiqo_pg_ai_report.sql_utils import SQLUtils
from aiqo_pg_ai_report.context import ContextLoader

DEFAULT_LANG = "fr"  # Default language for output, not for prompt file selection
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_AI_CALLS_UNLIMITED = -1

# Configure logging (default to INFO, can be overridden by CLI)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class PGAutoExplainAnalyzer:
    def __init__(self, args):
        self.args = args
        self.model = args.model
        self.skip_ai_analysis = args.skip_ai_analysis
        self.limit_ai_calls = args.limit_ai_calls
        self.ai_call_timeout = args.ai_call_timeout
        self.language = args.language
        self.only_seq_scan_ai_analysis = args.only_seq_scan_ai_analysis
        self.filter_strings = args.filter
        self.custom_prompt = args.custom_prompt
        self.target_query_mode = args.target_query_mode
        self.context_folder = args.context_folder  # Nouveau paramètre renommé
        self.directory_mode_active = args.directory_mode_active  # Nouveau: flag pour le mode répertoire


        # Initialize ContextLoader which handles loading prompts and all context/optimization files
        self.context_loader = ContextLoader(
            script_base_path=Path(__file__).parent, context_folder_cli_arg=self.context_folder
        )

        self.ai_caller = AiCaller(
            model=self.model,
            ai_call_timeout=self.ai_call_timeout,
            lang=self.language,
            prompts={},  # ContextLoader no longer has a 'prompts' dictionary; AiCaller no longer needs it.
            debug=args.debug
        )
        try:
            self.log_parser = self._create_log_parser(args.format)
        except ValueError as exc:
            logger.error(str(exc))
            sys.exit(1)
        # Pass the base path of the current script to ReportGenerator
        self.report_generator = ReportGenerator(self.context_loader.script_base_path, debug=args.debug)
        
        # Initialize the data processor
        from aiqo_pg_ai_report.report_data_processor import ReportDataProcessor
        self.data_processor = ReportDataProcessor()

    def _determine_ai_analysis_status(self, log_entry, query_code):
        """
        Détermine si l'analyse AI doit être effectuée et fournit un message de saut si elle est ignorée.
        Retourne (should_perform_ai_call: bool, ai_hints_message: str).
        """
        if self.skip_ai_analysis:
            logger.debug("Skipping AI analysis (skip_ai_analysis flag is true)")
            return False, ""

        if self.limit_ai_calls != -1 and (self.ai_caller.call_count >= self.limit_ai_calls):
            logger.warning("AI call limit reached. Skipping AI analysis for query")
            return False, ""

        # Vérifie les critères de filtre
        if self.filter_strings:
            match_found = False
            for filter_str in self.filter_strings:
                if (
                    filter_str.lower() in log_entry["job_name"].lower()
                    or filter_str.lower() in log_entry["query_name"].lower()
                    or filter_str.lower() in log_entry["query_text"].lower()
                    or filter_str.lower() in query_code.lower()
                ):
                    match_found = True
                    break
            if not match_found:
                logger.info(
                    f"Skipping AI analysis for query (code: {query_code[:6]}) as it does not match filter criteria."
                )
                return False, ""

        # Vérifie l'analyse AI uniquement pour les Seq Scan
        seq_scan_indicator = log_entry["execution_plan"].find("Seq Scan") != -1
        if self.only_seq_scan_ai_analysis and not seq_scan_indicator:
            logger.info("Skipping AI analysis for query without Seq Scan (only_seq_scan_ai_analysis is true)")
            return False, ""

        return True, ""

    def _perform_ai_call_and_get_hints(self, log_entry, query_code):
        """
        Effectue l'appel à l'API AI et retourne les indices ou un message d'échec.
        """
        full_prompt = self.context_loader.build_full_prompt_with_optimizations(
            plan=log_entry["execution_plan"],
            query_code=query_code,
            custom_prompt=self.custom_prompt,
            lang=self.language,
        )
        ai_hints_result = self.ai_caller.call_ai_provider(full_prompt)
        if ai_hints_result is None:
            return "AI analysis failed or timed out."
        return ai_hints_result

    def _process_parsed_log_entry(self, log_entry):
        query_text = log_entry["query_text"]
        query_code = SQLUtils.get_query_code(query_text)

        # Charge toujours les optimisations spécifiques à la requête dans le cache, indépendamment de l'analyse AI.
        # Cela garantit qu'elles sont disponibles pour l'affichage du rapport.
        self.context_loader.get_query_optimizations(query_code)

        should_perform_ai_call, ai_hints = self._determine_ai_analysis_status(log_entry, query_code)

        if should_perform_ai_call:
            ai_hints = self._perform_ai_call_and_get_hints(log_entry, query_code)
        # else ai_hints contient déjà le message de saut

        report = self.data_processor.create_report_entry(log_entry, query_code, ai_hints)
        self.data_processor.update_statistics(report)

    def run(self):
        # Rate limit variables are now handled within AiCaller, so these global assignments are removed.

        log_files = []
        report_filename = None

        if self.directory_mode_active:  # Utilise le nouveau flag
            directory = Path(self.args.log_filename)
            # La vérification de l'existence du répertoire est maintenant faite dans parse_cli_arguments

            log_files = list(directory.glob("*.log")) + list(directory.glob("*.gz")) + list(directory.glob("*.zip"))
            if not log_files:
                logger.error(f"No .log, .gz or .zip files found in directory: {self.args.log_filename}")
                sys.exit(1)  # Utiliser sys.exit(1) pour quitter proprement

            logger.info(f"Processing directory: {self.args.log_filename}")
            logger.info(f"Found files: {[str(f) for f in log_files]}")

            if self.args.report_filename:
                report_filename = self.args.report_filename
            else:
                report_filename = str(directory / f"{directory.name}_report.html")

        else:  # Single file mode
            log_file_path = Path(self.args.log_filename)
            # La vérification de l'existence du fichier est maintenant faite dans parse_cli_arguments
            log_files = [log_file_path]

            report_filename = (
                self.args.report_filename if self.args.report_filename else f"{self.args.log_filename}_report.html"
            )
            logger.info(f"Processing PostgreSQL log file {self.args.log_filename}")

        resolved_report_filename = Path(report_filename).resolve()
        logger.info(f"Output report: {resolved_report_filename}")

        # Load all contexts and optimizations using the ContextLoader
        self.context_loader.load_all_contexts(self.args.log_filename, self.directory_mode_active)

        if self.skip_ai_analysis:
            logger.info("Skipping AI Analysis")
        else:
            logger.info(f"Using model: {self.model}")
            logger.info(f"Maximum AI calls: {self.limit_ai_calls if self.limit_ai_calls != -1 else 'Unlimited'}")
            logger.info(f"AI API call timeout: {self.ai_call_timeout} seconds")
            logger.info(f"Language for AI output: {self.language}")
            logger.info(f"AI Analysis only for Seq Scan queries : {self.only_seq_scan_ai_analysis}")
            if self.custom_prompt:
                logger.info(f"Custom prompt provided: {self.custom_prompt}")
            # Updated log messages for DDL and server config context
            if self.context_loader.ddl_context:
                logger.info(f"DDL context loaded from file: {self.context_loader.optimization_base_path / 'DDL.txt'}")
            if self.context_loader.server_configuration_context:
                logger.info(
                    f"Server configuration context loaded from file: {self.context_loader.optimization_base_path / 'CONFIG.txt'}"
                )
            if self.context_loader.infra_context:
                logger.info(
                    f"Infrastructure context loaded from file: {self.context_loader.optimization_base_path / 'INFRA.txt'}"
                )
            # Log for context folder
            if self.context_loader.optimization_base_path:
                logger.info(f"Optimization context loaded from folder: {self.context_loader.optimization_base_path}")

        if self.target_query_mode:
            logger.info("Target Query Mode is ENABLED.")

        if self.filter_strings:
            logger.info(
                f"AI analysis will be filtered by: {', '.join(self.filter_strings)}. All queries will still be included in the report."
            )

        for log_file in log_files:
            for parsed_entry in self.log_parser.parse_log_file(log_file):
                self._process_parsed_log_entry(parsed_entry)

        # Get query stats from data processor
        query_stats_list = self.data_processor.get_query_stats_list()
        report_title = (
            "PostgreSQL Auto Explain Report"
            if self.skip_ai_analysis
            else f"PostgreSQL Auto Explain AI Report ({self.model}) "
        )

        # Passer les optimisations collectées au générateur de rapport
        self.report_generator.generate_report(
            str(resolved_report_filename),
            report_title,
            self.model,
            query_stats_list,
            self.data_processor.reports_by_day,
            self.data_processor.daily_query_stats,
            self.context_loader.query_optimizations_cache,  # Pass the query optimizations cache from ContextLoader
            self.context_loader.server_optimizations,  # Pass pre-loaded server optimizations from ContextLoader
            self.context_loader.event_optimizations,  # Pass pre-loaded event optimizations from ContextLoader
            self.context_loader.ddl_context,
            self.context_loader.server_configuration_context,
            self.context_loader.infra_context,
            self.skip_ai_analysis,  # Pass the skip_ai_analysis flag
        )

        self.ai_caller.show_stats()

    @staticmethod
    def _create_log_parser(log_format: str):
        log_format_normalized = log_format.lower()
        if log_format_normalized == "json":
            return JsonLogParser()
        if log_format_normalized == "text":
            return TextLogParser()
        if log_format_normalized == "yaml":
            raise ValueError(f"format {log_format_normalized} unsupported.")
        raise ValueError(f"format {log_format} unsupported.")


def parse_cli_arguments():
    parser = argparse.ArgumentParser(description="Process PostgreSQL log file and generate an analysis report.")
    parser.add_argument(
        "log_filename", nargs="?", help="Path to the PostgreSQL log file or directory containing log files."
    )  # Updated help text
    parser.add_argument(
        "-m", "--model", default=DEFAULT_MODEL, help=f"AI model to use for analysis (default: ${DEFAULT_MODEL})"
    )
    parser.add_argument(
        "-l",
        "--limit-ai-calls",
        type=int,
        default=DEFAULT_MAX_AI_CALLS_UNLIMITED,
        help=f"Maximum number of AI calls to make. Use -1 for unlimited (default: ${DEFAULT_MAX_AI_CALLS_UNLIMITED})",
    )
    parser.add_argument(
        "--ai-call-timeout",
        type=int,
        default=DEFAULT_AI_CALL_TIMEOUT,
        help=f"Timeout for AI API calls in seconds (default: ${DEFAULT_AI_CALL_TIMEOUT})",
    )
    parser.add_argument("--language", default=DEFAULT_LANG, help=f"Language for AI output (default: ${DEFAULT_LANG})")
    parser.add_argument(
        "-s",
        "--skip_ai_analysis",
        action="store_true",
        help="Skips the AI analysis and only generates the HTML report (default: false)",
    )
    parser.add_argument(
        "-o",
        "--only-seq-scan-ai-analysis",
        action="store_true",
        help="Enables AI Analysis only for queries with Seq Scan (default: false)",
    )
    parser.add_argument(
        "-f",
        "--filter",
        action="append",
        help="Perform AI analysis only for queries that contain the specified string in the comment, SQL, or query code. Can be specified multiple times. All queries will still be included in the report.",
    )
    parser.add_argument(
        "-c", "--custom-prompt", type=str, default=None, help="Add a custom prompt to the default AI prompt (optional)"
    )
    parser.add_argument(
        "-r", "--report-filename", type=str, default=None, help="Override the HTML report filename (optional)"
    )
    parser.add_argument(
        "--target-query-mode",
        action="store_true",
        default=False,
        help="Enables target query mode for analysis (default: false)",
    )
    parser.add_argument(
        "--context-folder",
        "-cf",
        type=str,
        default=None,
        help="Path to a directory containing optimization context files (SERVER.txt, EVENTS.txt, query-specific .txt files). Overrides the default 'CONTEXT' subfolder behavior.",
    )
    parser.add_argument(
        "--format",
        "-fmt",
        type=str,
        default="text",
        choices=["json", "text", "yaml"],
        help="Log format to parse: text (default), json, yaml (unsupported).",
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging (default: false)")

    args, unknown_args = parser.parse_known_args()

    if unknown_args:
        logger.warning(f"Unrecognized arguments: {unknown_args}. These will be ignored.")

    # New logic for path validation and directory mode detection
    if not args.log_filename:
        parser.error("The 'log_filename' argument is required. Please provide a path to a log file or a directory.")

    log_path = Path(args.log_filename)

    if not log_path.exists():
        logger.error(f"Erreur: Le chemin spécifié '{args.log_filename}' n'existe pas.")
        sys.exit(1)

    args.directory_mode_active = log_path.is_dir()

    if args.directory_mode_active:
        logger.info(f"L'exécution est en mode répertoire pour le chemin : {args.log_filename}")
    else:
        if not log_path.is_file():  # If it's not a directory, it must be a file
            logger.error(
                f"Erreur: Le chemin spécifié '{args.log_filename}' n'est ni un fichier ni un répertoire valide."
            )
            sys.exit(1)
        logger.info(f"L'exécution est en mode fichier unique pour le chemin : {args.log_filename}")

    return args


def main():
    args = parse_cli_arguments()

    if args.debug:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("ai_caller").setLevel(logging.DEBUG)
        logging.getLogger("context").setLevel(logging.DEBUG)
        logging.getLogger("log_parser").setLevel(logging.DEBUG)
        logging.getLogger("report_generator").setLevel(logging.DEBUG)
        logging.getLogger("sql_utils").setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled.")

    analyzer = PGAutoExplainAnalyzer(args)
    analyzer.run()


if __name__ == "__main__":
    main()
