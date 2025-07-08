#!/usr/bin/env python

import argparse
import hashlib
import logging
import re
from collections import defaultdict
from pathlib import Path

import sqlparse

# Import classes and necessary constants from their new modules
from ai_caller import AiCaller, DEFAULT_AI_CALL_TIMEOUT, DEFAULT_MODEL_TEMPERATURE
from log_parser import LogParser
from report_generator import ReportGenerator, QUERY_NAME_LIMIT

DEFAULT_LANG = "fr" # Default language for output, not for prompt file selection
DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_MAX_AI_CALLS_UNLIMITED = -1

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def normalize_sql(sql):
    # Formater le SQL avec sqlparse
    formatted_sql = sqlparse.format(sql, strip_comments=True, reindent=True, strip_whitespace=True)

    # Remplacer les constantes numériques et les chaînes de caractères par '?'
    formatted_sql = re.sub(r'\b\d+\b', '?', formatted_sql)  # Nombres
    formatted_sql = re.sub(r"'[^']*'", '?', formatted_sql)  # Chaînes de caractères

    return formatted_sql


def get_query_code(query):
    normalized_query = normalize_sql(query)
    value_str = str(normalized_query).encode('utf-8')
    return hashlib.sha256(value_str).hexdigest().upper()


class PGAutoExplainAnalyzer:
    def __init__(self, args):
        self.args = args
        self.model = args.model
        self.skip_ai_analysis = args.skip_ai_analysis
        self.limit_ai_calls = args.limit_ai_calls
        self.ai_call_timeout = args.ai_call_timeout
        self.language = args.language
        self.temperature = args.temperature
        self.only_seq_scan_ai_analysis = args.only_seq_scan_ai_analysis
        self.filter_strings = args.filter
        self.custom_prompt = args.custom_prompt
        self.ddl_context = self._load_ddl_context(args.sql_context_file)
        self.target_query_mode = args.target_query_mode
        self.optimization_files = args.optimization_files # Nouvelle variable membre
        if self.optimization_files:
            optimization_path = Path(self.optimization_files)
            if not optimization_path.exists():
                raise FileNotFoundError(f"Le chemin spécifié pour les fichiers d'optimisation n'existe pas : {self.optimization_files}")
            if not optimization_path.is_dir():
                logger.warning(f"Le chemin spécifié pour les fichiers d'optimisation n'est pas un répertoire : {self.optimization_files}. Il sera traité comme un fichier unique si applicable, mais les optimisations par code de requête ne seront pas chargées.")


        self.prompts = self._load_prompts()
        if not self.prompts:
            logger.error("Failed to load prompts. Exiting.")
            exit(1)

        self.ai_caller = AiCaller(
            model=self.model,
            temperature=self.temperature,
            ai_call_timeout=self.ai_call_timeout,
            lang=self.language,
            prompts=self.prompts
        )
        self.log_parser = LogParser()
        # Pass the base path of the current script to ReportGenerator
        self.report_generator = ReportGenerator(Path(__file__).parent)

        self.all_reports = []
        self.reports_by_day = defaultdict(list)
        self.all_query_stats_dict = {}
        # New data structure for daily query statistics
        self.daily_query_stats = defaultdict(lambda: {"total_queries": 0, "cumulated_time": 0.0, "queries_by_code": defaultdict(float)})
        self.final_analysis_result = ""

    def _load_ddl_context(self, sql_context_file):
        if sql_context_file:
            try:
                with open(sql_context_file, "r", encoding="utf-8") as ddl_file:
                    ddl_context = ddl_file.read()
                logger.info(f"Loaded DDL context from: {sql_context_file}")
                return ddl_context
            except Exception as e:
                logger.error(f"Could not read DDL context file '{sql_context_file}': {e}")
        return None

    def _load_prompts(self):
        current_prompts = {}
        current_prompt = None
        current_content = []
        lang_file_path = Path(__file__).parent / 'prompts/prompts.txt'

        try:
            with open(lang_file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    line = line.strip()
                    if line.startswith('[') and line.endswith(']'):
                        if current_prompt:
                            current_prompts[current_prompt] = '\n'.join(current_content).strip()
                        current_prompt = line[1:-1]
                        current_content = []
                    else:
                        current_content.append(line)

            if current_prompt:
                current_prompts[current_prompt] = '\n'.join(current_content).strip()

            if not current_prompts:
                logger.error(f"Failed to load prompts from: {lang_file_path}. Exiting.")
                exit(1)
        except FileNotFoundError:
            logger.error(f"Prompts file not found: {lang_file_path}")
            exit(1)
        except Exception as e:
            logger.error(f"Error reading prompts file: {e}")
            exit(1)
        return current_prompts

    def _load_optimizations_for_queries(self, query_codes: list) -> dict:
        """
        Charge les textes d'optimisation pour une liste de codes de requête.
        Chaque code de requête correspond à un fichier <query_code>.txt dans le répertoire d'optimisation.
        Chaque ligne du fichier est au format <yyyy-mm-dd>:<texte d'optimisation>.
        Retourne un dictionnaire où les clés sont les codes de requête et les valeurs sont des listes
        de textes d'optimisation pour cette requête, triées par date.
        Ex: { "query_code_1": ["optimisation_text_1", "optimisation_text_2"], ... }
        """
        if not self.optimization_files:
            logger.debug("Le chemin des fichiers d'optimisation n'est pas spécifié. Aucune optimisation ne sera chargée.")
            return {}

        optimizations_data = {}
        optimization_base_path = Path(self.optimization_files)

        if not optimization_base_path.is_dir():
            logger.warning(f"Le chemin spécifié pour les fichiers d'optimisation '{self.optimization_files}' n'est pas un répertoire. Impossible de charger les optimisations par code de requête.")
            return {}

        for query_code in query_codes:
            file_path = optimization_base_path / f"{query_code}.txt"
            if file_path.is_file():
                # Store as list of (date, text) tuples to sort later
                query_optimizations_with_dates = []
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            parts = line.split(':', 1) # Split only on the first colon
                            if len(parts) == 2:
                                date = parts[0].strip()
                                optimization_text = parts[1].strip()
                                query_optimizations_with_dates.append((date, optimization_text))
                            else:
                                logger.warning(f"Ligne mal formatée dans '{file_path}': '{line}'. Format attendu: YYYY-MM-DD:Optimisation text.")
                    
                    if query_optimizations_with_dates:
                        # Sort by date and extract only the optimization texts
                        sorted_optimizations = [text for date, text in sorted(query_optimizations_with_dates, key=lambda x: x[0])]
                        optimizations_data[query_code] = sorted_optimizations
                    else:
                        logger.debug(f"Aucune optimisation valide trouvée dans '{file_path}'.")
                except Exception as e:
                    logger.error(f"Erreur lors de la lecture du fichier d'optimisation '{file_path}': {e}")
            else:
                logger.debug(f"Fichier d'optimisation non trouvé pour la requête '{query_code}': '{file_path}'")
        return optimizations_data


    def _process_parsed_log_entry(self, parsed_result):
        query_name = parsed_result["query_name"]
        job_name = parsed_result["job_name"]
        query_text = parsed_result["query_text"]
        query_code = get_query_code(query_text)

        title = job_name + " " + query_name
        execution_plan = parsed_result["execution_plan"]
        timestamp = parsed_result["timestamp"]
        day = timestamp[:10] # Extract YYYY-MM-DD
        query = query_text
        ai_hints = "" # Initialize to empty string
        seq_scan_indicator = (execution_plan.find("Seq Scan") != -1)
        duration = parsed_result["duration"]

        should_perform_ai_call = True # Flag to control if AI call should be made

        # 1. Check if AI analysis is globally skipped
        if self.skip_ai_analysis:
            ai_hints = "AI analysis skipped (CLI flag --skip_ai_analysis)."
            should_perform_ai_call = False
            logger.debug("Skipping AI analysis (skip_ai_analysis flag is true)")

        # 2. Check filter criteria (if not already skipped globally)
        if should_perform_ai_call and self.filter_strings:
            match_found = False
            for filter_str in self.filter_strings:
                if (filter_str.lower() in job_name.lower() or
                    filter_str.lower() in query_name.lower() or
                    filter_str.lower() in query_text.lower() or
                    filter_str.lower() in query_code.lower()):
                    match_found = True
                    break
            if not match_found:
                ai_hints = "AI analysis skipped due to filter criteria."
                should_perform_ai_call = False
                logger.info(f"Skipping AI analysis for query (code: {query_code[:6]}) as it does not match filter criteria.")

        # 3. Check max AI calls limit (if not already skipped)
        if should_perform_ai_call and self.limit_ai_calls != -1 and (self.ai_caller.call_count >= self.limit_ai_calls):
            ai_hints = "AI analysis skipped (AI call limit reached)."
            should_perform_ai_call = False
            logger.warning(f"AI call limit reached. Skipping AI analysis for query")

        # 4. Check AI only for Seq Scan (if not already skipped)
        if should_perform_ai_call and self.only_seq_scan_ai_analysis and not seq_scan_indicator:
            ai_hints = "AI analysis skipped (only for Seq Scan queries)."
            should_perform_ai_call = False
            logger.info("Skipping AI analysis for query without Seq Scan (only_seq_scan_ai_analysis is true)")

        # 5. Perform AI call if all conditions allow
        if should_perform_ai_call:
            ai_hints_result = self.ai_caller.call_ai_for_plan_analysis(
                parsed_result["execution_plan"], custom_prompt=self.custom_prompt, ddl_context=self.ddl_context
            )
            if ai_hints_result is None:
                ai_hints = "AI analysis failed or timed out."
            else:
                ai_hints = ai_hints_result

        report = {
            "title": title,
            "chatgpt_hints": ai_hints,
            "plan": execution_plan,
            "query_text": query,
            "query_timestamp": timestamp,
            "query_name": query_name,
            "job_name": job_name,
            "code": query_code,
            "day": day,
            "seq_scan_indicator": seq_scan_indicator,
            "duration" : duration
        }

        self.all_reports.append(report)
        self.reports_by_day[report["day"]].append(report)

        # Update query_stats in-place (global stats across all days)
        if query_code not in self.all_query_stats_dict:
            self.all_query_stats_dict[query_code] = {
                "code": query_code,
                "name": report["query_name"],
                "count": 1,
                "cumulated_time": duration
            }
        else:
            self.all_query_stats_dict[query_code]["count"] += 1
            self.all_query_stats_dict[query_code]["cumulated_time"] += duration

        # Update new daily_query_stats data structure
        self.daily_query_stats[day]["total_queries"] += 1
        self.daily_query_stats[day]["cumulated_time"] += duration
        self.daily_query_stats[day]["queries_by_code"][query_code] += duration


    def run(self):
        # Rate limit variables are now handled within AiCaller, so these global assignments are removed.

        if self.args.directory_mode:
            directory = Path(self.args.log_filename)
            if not directory.is_dir():
                logger.error(f"Specified directory does not exist: {self.args.log_filename}")
                exit(1)

            log_files = list(directory.glob("*.log")) + list(directory.glob("*.gz")) + list(directory.glob("*.zip"))
            if not log_files:
                logger.error(f"No .log, .gz or .zip files found in directory: {self.args.log_filename}")
                exit(1)

            logger.info(f"Processing directory: {self.args.log_filename}")
            logger.info(f"Found files: {[str(f) for f in log_files]}")
            
            if self.args.report_filename:
                report_filename = self.args.report_filename
            else:
                report_filename = str(directory / f"{directory.name}_report.html")

        else: # Single file mode
            log_file_path = Path(self.args.log_filename)
            if not log_file_path.is_file():
                logger.error(f"Specified log file does not exist: {self.args.log_filename}")
                exit(1)
            log_files = [log_file_path]

            report_filename = self.args.report_filename if self.args.report_filename else f"{self.args.log_filename}_report.html"
            logger.info(f"Processing PostgreSQL log file {self.args.log_filename}")

        resolved_report_filename = Path(report_filename).resolve()
        logger.info(f"Output report: {resolved_report_filename}")

        if self.skip_ai_analysis:
            logger.info("Skipping AI Analysis")
        else:
            logger.info(f"Using model: {self.model}")
            logger.info(f"Maximum AI calls: {self.limit_ai_calls if self.limit_ai_calls != -1 else 'Unlimited'}")
            logger.info(f"AI API call timeout: {self.ai_call_timeout} seconds")
            logger.info(f"Language for AI output: {self.language}")
            logger.info(f"Model temperature : {self.temperature}")
            logger.info(f"AI Analysis only for Seq Scan queries : {self.only_seq_scan_ai_analysis}")
            if self.custom_prompt:
                logger.info(f"Custom prompt provided: {self.custom_prompt}")
            if self.ddl_context:
                logger.info(f"DDL context loaded from file: {self.args.sql_context_file}")
        
        if self.target_query_mode:
            logger.info("Target Query Mode is ENABLED.")

        if self.filter_strings:
            logger.info(f"AI analysis will be filtered by: {', '.join(self.filter_strings)}. All queries will still be reported.")

        for log_file in log_files:
            for parsed_entry in self.log_parser.parse_log_file(log_file):
                self._process_parsed_log_entry(parsed_entry)

        if not self.skip_ai_analysis:
            self.final_analysis_result = self.ai_caller.call_ai_for_final_analysis(self.all_reports)
        else:
            self.final_analysis_result = ""

        # Convert query_stats dict to sorted list for the report
        query_stats_list = sorted(self.all_query_stats_dict.values(), key=lambda x: x["cumulated_time"], reverse=True)
        report_title = "PostgreSQL Auto Explain Report" if self.skip_ai_analysis else f"PostgreSQL Auto Explain AI Report ({self.model}) "

        # Charger les optimisations de requêtes
        all_query_codes = list(self.all_query_stats_dict.keys())
        query_optimizations_data = self._load_optimizations_for_queries(all_query_codes)

        self.report_generator.generate_report(
            str(resolved_report_filename),
            report_title,
            self.final_analysis_result,
            self.model,
            query_stats_list,
            self.reports_by_day,
            self.daily_query_stats, # Pass the new data structure
            query_optimizations_data # Nouveau paramètre passé au template
        )


def parse_cli_arguments():
    parser = argparse.ArgumentParser(description="Process PostgreSQL log file and generate an analysis report.")
    parser.add_argument("log_filename", nargs="?", help="Path to the PostgreSQL log file")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"AI model to use for analysis (default: ${DEFAULT_MODEL})")
    parser.add_argument("-l", "--limit-ai-calls", type=int, default=DEFAULT_MAX_AI_CALLS_UNLIMITED,
                        help=f"Maximum number of AI calls to make. Use -1 for unlimited (default: ${DEFAULT_MAX_AI_CALLS_UNLIMITED})")
    parser.add_argument( "--ai-call-timeout", type=int, default=DEFAULT_AI_CALL_TIMEOUT,
                        help=f"Timeout for AI API calls in seconds (default: ${DEFAULT_AI_CALL_TIMEOUT})")
    parser.add_argument("--language", default=DEFAULT_LANG,
                        help=f"Language for AI output (default: ${DEFAULT_LANG})")
    parser.add_argument("--temperature", type=float, default=DEFAULT_MODEL_TEMPERATURE,
                        help=f"Temperature for the AI model (default: ${DEFAULT_MODEL_TEMPERATURE})")
    parser.add_argument("-s", "--skip_ai_analysis", action="store_true",
                        help="Skips the AI analysis and only generates the HTML report (default: false)")
    parser.add_argument("-o", "--only-seq-scan-ai-analysis", action="store_true",
                        help="Enables AI Analysis only for queries with Seq Scan (default: false)")
    parser.add_argument("-f", "--filter", action="append",
                        help="Perform AI analysis only for queries that contain the specified string in the comment, SQL, or query code. Can be specified multiple times. All queries will still be included in the report.")
    parser.add_argument("-c", "--custom-prompt", type=str, default=None,
                        help="Add a custom prompt to the default AI prompt (optional)")
    parser.add_argument("--sql-context-file", type=str, default=None,
                        help="Specify a DDL SQL file whose content will be added to the prompt (optional)")
    parser.add_argument("-r", "--report-filename", type=str, default=None,
                        help="Override the HTML report filename (optional)")
    parser.add_argument("-d","--directory-mode", action="store_true", default=False,
                        help="Process all .log and .zip files in the directory specified as the main positional argument")
    parser.add_argument("--target-query-mode", action="store_true", default=False,
                        help="Enables target query mode for analysis (default: false)")
    parser.add_argument("--optimization-files", "-of", type=str, default=None,
                        help="Chemin vers un répertoire contenant des fichiers SQL d'optimisation ou un fichier SQL unique. Ces fichiers seront utilisés comme contexte pour l'analyse des plans d'exécution.")


    args, unknown_args = parser.parse_known_args()

    if unknown_args:
        logger.warning(f"Unrecognized arguments: {unknown_args}. These will be ignored.")

    return args


def main():
    args = parse_cli_arguments()
    analyzer = PGAutoExplainAnalyzer(args)
    analyzer.run()

    logger.info(f"Total input tokens processed: {analyzer.ai_caller.total_input_tokens}")
    logger.info(f"Total output tokens processed: {analyzer.ai_caller.total_output_tokens}")
    logger.info(f"Estimated total cost: ${analyzer.ai_caller.total_cost:.4f}")


if __name__ == "__main__":
    main()
