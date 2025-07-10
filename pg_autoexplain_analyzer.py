#!/usr/bin/env python

import argparse
import hashlib
import logging
import re
import sys # Import sys for exit
from collections import defaultdict
from pathlib import Path

import sqlparse

# Import classes and necessary constants from their new modules
from ai_caller import AiCaller, DEFAULT_AI_CALL_TIMEOUT, DEFAULT_MODEL_TEMPERATURE
from log_parser import LogParser
from report_generator import ReportGenerator, QUERY_NAME_LIMIT

DEFAULT_LANG = "fr" # Default language for output, not for prompt file selection
DEFAULT_MODEL = "gemini-2.5-flash"
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
        self.ddl_context = None # Chargé dans run()
        self.server_configuration_context = None # Chargé dans run()
        self.infra_context = None # Nouveau: Chargé dans run()
        self.target_query_mode = args.target_query_mode
        self.context_folder = args.context_folder # Nouveau paramètre renommé
        self.directory_mode_active = args.directory_mode_active # Nouveau: flag pour le mode répertoire

        # Initialisation des variables pour les optimisations
        self.server_optimizations = []
        self.event_optimizations = []
        self.query_optimizations_cache = {} # Cache pour les optimisations spécifiques aux requêtes
        self.optimization_base_path = None # Sera défini dans run()

        self.prompts = self._load_prompts()
        if not self.prompts:
            logger.error("Failed to load prompts. Exiting.")
            sys.exit(1) # Utiliser sys.exit(1) pour quitter proprement

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

    def _load_ddl_context(self, file_path: Path):
        """
        Charge le contenu d'un fichier DDL.
        Arrête l'exécution si le fichier n'existe pas ou ne peut pas être lu.
        """
        try:
            if not file_path.is_file():
                logger.error(f"DDL context file not found: '{file_path}'. It is required if a context folder is active.")
                sys.exit(1) # Arrête l'exécution si le fichier n'existe pas
            with open(file_path, "r", encoding="utf-8") as ddl_file:
                ddl_context = ddl_file.read()
            logger.info(f"Loaded DDL context from: {file_path}")
            return ddl_context
        except Exception as e:
            logger.error(f"Could not read DDL context file '{file_path}': {e}")
            sys.exit(1) # Arrête l'exécution en cas d'erreur de lecture

    def _load_server_configuration(self, file_path: Path):
        """
        Charge le contenu d'un fichier de configuration de serveur.
        Arrête l'exécution si le fichier n'existe pas ou ne peut pas être lu.
        """
        try:
            if not file_path.is_file():
                logger.error(f"Server configuration file not found: '{file_path}'. It is required if a context folder is active.")
                sys.exit(1) # Arrête l'exécution si le fichier n'existe pas
            with open(file_path, "r", encoding="utf-8") as config_file:
                config_content = config_file.read()
            logger.info(f"Loaded server configuration from: {file_path}")
            return config_content
        except Exception as e:
            logger.error(f"Could not read server configuration file '{file_path}': {e}")
            sys.exit(1) # Arrête l'exécution en cas d'erreur de lecture

    def _load_infra_context(self, file_path: Path):
        """
        Charge le contenu d'un fichier d'infrastructure.
        Arrête l'exécution si le fichier n'existe pas ou ne peut pas être lu.
        """
        try:
            if not file_path.is_file():
                logger.error(f"Infrastructure context file not found: '{file_path}'. It is required if a context folder is active.")
                sys.exit(1) # Arrête l'exécution si le fichier n'existe pas
            with open(file_path, "r", encoding="utf-8") as infra_file:
                infra_context = infra_file.read()
            logger.info(f"Loaded infrastructure context from: {file_path}")
            return infra_context
        except Exception as e:
            logger.error(f"Could not read infrastructure context file '{file_path}': {e}")
            sys.exit(1) # Arrête l'exécution en cas d'erreur de lecture

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
                sys.exit(1)
        except FileNotFoundError:
            logger.error(f"Prompts file not found: {lang_file_path}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error reading prompts file: {e}")
            sys.exit(1)
        return current_prompts

    def _parse_optimization_file(self, file_path):
        """
        Helper pour lire et parser un fichier d'optimisation.
        Retourne une liste de dictionnaires [{"date": "YYYY-MM-DD", "text": "opt_text"}, ...].
        """
        parsed_opts = []
        if file_path.is_file():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            date = parts[0].strip()
                            optimization_text = parts[1].strip()
                            parsed_opts.append({"date": date, "text": optimization_text})
                        else:
                            logger.warning(f"Ligne mal formatée dans '{file_path}': '{line}'. Format attendu: YYYY-MM-DD:Optimisation text.")
                # Tri par date pour une meilleure lisibilité
                return sorted(parsed_opts, key=lambda x: x["date"])
            except Exception as e:
                logger.error(f"Erreur lors de la lecture du fichier d'optimisation '{file_path}': {e}")
        else:
            logger.debug(f"Fichier d'optimisation non trouvé : '{file_path}'")
        return []

    def _load_general_optimizations(self):
        """
        Charge les optimisations générales du serveur (SERVER.txt) et des événements (EVENTS.txt)
        dans les variables d'instance.
        """
        if not self.optimization_base_path or not self.optimization_base_path.is_dir():
            logger.debug("Le chemin des fichiers d'optimisation n'est pas défini ou n'est pas un répertoire. Aucune optimisation générale ne sera chargée.")
            return

        server_file_path = self.optimization_base_path / "SERVER.txt"
        self.server_optimizations = self._parse_optimization_file(server_file_path)
        if self.server_optimizations:
            logger.info(f"Optimisations serveur chargées depuis : {server_file_path}")

        events_file_path = self.optimization_base_path / "EVENTS.txt"
        self.event_optimizations = self._parse_optimization_file(events_file_path)
        if self.event_optimizations:
            logger.info(f"Optimisations événements chargées depuis : {events_file_path}")


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

        # Préparer le contexte des optimisations déjà appliquées pour l'IA
        applied_optimizations_context = ""
        current_query_opts = []

        if self.optimization_base_path and self.optimization_base_path.is_dir():
            # Charger les optimisations spécifiques à la requête à la demande et les mettre en cache
            if query_code not in self.query_optimizations_cache:
                file_path = self.optimization_base_path / f"{query_code[:6]}.txt"
                self.query_optimizations_cache[query_code] = self._parse_optimization_file(file_path)
                if self.query_optimizations_cache[query_code]:
                    logger.debug(f"Optimisations de requête chargées pour {query_code[:6]} depuis : {file_path}")
            
            current_query_opts = self.query_optimizations_cache.get(query_code, [])

            # Construire la chaîne de contexte pour l'IA
            if current_query_opts or self.server_optimizations:
                applied_optimizations_context += "The following optimizations have already been applied to the system or this specific query:\n"
                if self.server_optimizations:
                    applied_optimizations_context += "  - Server-wide optimizations:\n"
                    for opt in self.server_optimizations:
                        applied_optimizations_context += f"    - {opt['date']}: {opt['text']}\n"
                if current_query_opts:
                    applied_optimizations_context += "  - Query-specific optimizations for this query:\n"
                    for opt in current_query_opts:
                        applied_optimizations_context += f"    - {opt['date']}: {opt['text']}\n"
                applied_optimizations_context += "\n" # Ajouter un saut de ligne pour la séparation

        # 5. Perform AI call if all conditions allow
        if should_perform_ai_call:
            # Combiner custom_prompt et applied_optimizations_context
            full_custom_prompt = self.custom_prompt if self.custom_prompt else ""
            if applied_optimizations_context:
                full_custom_prompt = applied_optimizations_context + (f"\n{full_custom_prompt}" if full_custom_prompt else "")

            ai_hints_result = self.ai_caller.call_ai_for_plan_analysis(
                parsed_result["execution_plan"],
                custom_prompt=full_custom_prompt, # Passer le prompt combiné
                ddl_context=self.ddl_context,
                server_config_context=self.server_configuration_context, # Passer le contexte de configuration du serveur
                infra_context=self.infra_context # Passer le nouveau contexte d'infrastructure
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

        log_files = []
        report_filename = None
        
        if self.directory_mode_active: # Utilise le nouveau flag
            directory = Path(self.args.log_filename)
            # La vérification de l'existence du répertoire est maintenant faite dans parse_cli_arguments

            log_files = list(directory.glob("*.log")) + list(directory.glob("*.gz")) + list(directory.glob("*.zip"))
            if not log_files:
                logger.error(f"No .log, .gz or .zip files found in directory: {self.args.log_filename}")
                sys.exit(1) # Utiliser sys.exit(1) pour quitter proprement

            logger.info(f"Processing directory: {self.args.log_filename}")
            logger.info(f"Found files: {[str(f) for f in log_files]}")
            
            if self.args.report_filename:
                report_filename = self.args.report_filename
            else:
                report_filename = str(directory / f"{directory.name}_report.html")

        else: # Single file mode
            log_file_path = Path(self.args.log_filename)
            # La vérification de l'existence du fichier est maintenant faite dans parse_cli_arguments
            log_files = [log_file_path]

            report_filename = self.args.report_filename if self.args.report_filename else f"{self.args.log_filename}_report.html"
            logger.info(f"Processing PostgreSQL log file {self.args.log_filename}")

        resolved_report_filename = Path(report_filename).resolve()
        logger.info(f"Output report: {resolved_report_filename}")

        # Determine the base path for context files (SERVER.txt, EVENTS.txt, query-specific)
        context_base_path = None
        if self.args.context_folder: # If --context-folder is explicitly provided
            context_base_path = Path(self.args.context_folder)
            logger.info(f"Using specified context folder: {context_base_path}")
        elif self.args.log_filename: # Determine default context folder if log_filename is provided
            if self.directory_mode_active: # Utilise le nouveau flag
                context_base_path = Path(self.args.log_filename) / "CONTEXT"
                logger.info(f"Using default context folder for directory mode: {context_base_path}")
            else:
                context_base_path = Path(self.args.log_filename).parent / "CONTEXT"
                logger.info(f"Using default context folder for single file mode: {context_base_path}")
        else:
            logger.warning("No log file specified, cannot determine default context folder. No optimization context will be loaded.")
        
        self.optimization_base_path = context_base_path # Assign to instance variable

        # Validate and load general optimizations and other context files
        if self.optimization_base_path:
            if not self.optimization_base_path.exists():
                logger.warning(f"Le chemin spécifié pour le dossier de contexte n'existe pas : {self.optimization_base_path}. Aucune optimisation ni fichier de contexte ne sera chargé.")
                self.optimization_base_path = None # Clear it if it doesn't exist
            elif not self.optimization_base_path.is_dir():
                logger.warning(f"Le chemin spécifié pour le dossier de contexte n'est pas un répertoire : {self.optimization_base_path}. Les optimisations et fichiers de contexte ne seront pas chargés.")
                self.optimization_base_path = None # Clear it if it's not a directory
            else:
                # Load general optimizations (SERVER.txt, EVENTS.txt)
                self._load_general_optimizations()

                # Load DDL.txt, CONFIG.txt, and INFRA.txt from the context folder
                # These calls will exit if the files are not found or unreadable, as per the requirement.
                self.ddl_context = self._load_ddl_context(self.optimization_base_path / "DDL.txt")
                self.server_configuration_context = self._load_server_configuration(self.optimization_base_path / "CONFIG.txt")
                self.infra_context = self._load_infra_context(self.optimization_base_path / "INFRA.txt") # Nouveau: Chargement de INFRA.txt

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
            # Updated log messages for DDL and server config context
            if self.ddl_context:
                logger.info(f"DDL context loaded from file: {self.optimization_base_path / 'DDL.txt'}")
            if self.server_configuration_context:
                logger.info(f"Server configuration context loaded from file: {self.optimization_base_path / 'CONFIG.txt'}")
            if self.infra_context: # Nouveau: Log pour INFRA.txt
                logger.info(f"Infrastructure context loaded from file: {self.optimization_base_path / 'INFRA.txt'}")
            # Log for context folder
            if self.optimization_base_path:
                logger.info(f"Optimization context loaded from folder: {self.optimization_base_path}")
        
        if self.target_query_mode:
            logger.info("Target Query Mode is ENABLED.")

        if self.filter_strings:
            logger.info(f"AI analysis will be filtered by: {', '.join(self.filter_strings)}. All queries will still be included in the report.")

        for log_file in log_files:
            for parsed_entry in self.log_parser.parse_log_file(log_file):
                self._process_parsed_log_entry(parsed_entry)

        # Convert query_stats dict to sorted list for the report
        query_stats_list = sorted(self.all_query_stats_dict.values(), key=lambda x: x["cumulated_time"], reverse=True)
        report_title = "PostgreSQL Auto Explain Report" if self.skip_ai_analysis else f"PostgreSQL Auto Explain AI Report ({self.model}) "

        # Passer les optimisations collectées au générateur de rapport
        self.report_generator.generate_report(
            str(resolved_report_filename),
            report_title,
            self.model,
            query_stats_list,
            self.reports_by_day,
            self.daily_query_stats,
            self.query_optimizations_cache, # Passer le cache des optimisations de requêtes
            self.server_optimizations,    # Passer les optimisations serveur pré-chargées
            self.event_optimizations      # Passer les optimisations événements pré-chargées
        )


def parse_cli_arguments():
    parser = argparse.ArgumentParser(description="Process PostgreSQL log file and generate an analysis report.")
    parser.add_argument("log_filename", nargs="?", help="Path to the PostgreSQL log file or directory containing log files.") # Updated help text
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
    parser.add_argument("-r", "--report-filename", type=str, default=None,
                        help="Override the HTML report filename (optional)")
    parser.add_argument("--target-query-mode", action="store_true", default=False,
                        help="Enables target query mode for analysis (default: false)")
    parser.add_argument("--context-folder", "-cf", type=str, default=None,
                        help="Path to a directory containing optimization context files (SERVER.txt, EVENTS.txt, query-specific .txt files). Overrides the default 'CONTEXT' subfolder behavior.")


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
        if not log_path.is_file(): # If it's not a directory, it must be a file
            logger.error(f"Erreur: Le chemin spécifié '{args.log_filename}' n'est ni un fichier ni un répertoire valide.")
            sys.exit(1)
        logger.info(f"L'exécution est en mode fichier unique pour le chemin : {args.log_filename}")

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
