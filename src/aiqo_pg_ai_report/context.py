import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class ContextLoader:
    def __init__(self, script_base_path: Path, context_folder_cli_arg: str = None):
        self.script_base_path = script_base_path
        self.context_folder_cli_arg = context_folder_cli_arg  # The raw string from CLI
        self.optimization_base_path = None  # Will be Path object after load_all_contexts
        self.ddl_context = None
        self.server_configuration_context = None
        self.project_context = None
        self.server_optimizations = []
        self.event_optimizations = []
        self.query_optimizations_cache = {}
        self.system_prompt = None
        self.format_prompt = None

        self._load_ai_instruction_prompts()  # Load AI instruction prompts

    def _load_file_content(self, file_path: Path, context_name: str, required: bool = False):
        """Helper to load content from a file."""
        try:
            if not file_path.is_file():
                if required:
                    logger.error(
                        f"{context_name} file not found: '{file_path}'. It is required if a context folder is active."
                    )
                    sys.exit(1)
                else:
                    logger.debug(f"{context_name} file not found (optional): '{file_path}'")
                    return None
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            logger.info(f"Loaded {context_name} from: {file_path}")
            return content
        except Exception as e:
            logger.error(f"Could not read {context_name} file '{file_path}': {e}")
            sys.exit(1)

    def _load_ai_instruction_prompts(self):
        """Loads the system, format, and main plan analysis prompts."""
        system_file_path = self.script_base_path / "prompts/SYSTEM.txt"
        format_file_path = self.script_base_path / "prompts/FORMAT.txt"

        self.system_prompt = self._load_file_content(system_file_path, "System prompt", required=True)
        self.format_prompt = self._load_file_content(format_file_path, "Format prompt", required=True)

        if not (self.system_prompt and self.format_prompt):
            logger.error("Failed to load all required AI instruction prompts. Exiting.")
            sys.exit(1)
        logger.info("Loaded system and format prompts.")

    def _parse_optimization_file(self, file_path: Path):
        """Helper to read and parse an optimization file."""
        parsed_opts = []
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            date = parts[0].strip()
                            optimization_text = parts[1].strip()
                            parsed_opts.append({"date": date, "text": optimization_text})
                        else:
                            logger.warning(
                                f"Ligne mal formatée dans '{file_path}': '{line}'. Format attendu: YYYY-MM-DD:Optimisation text."
                            )
                # Sort by date for better readability
                return sorted(parsed_opts, key=lambda x: x["date"])
            except Exception as e:
                logger.error(f"Erreur lors de la lecture du fichier d'optimisation '{file_path}': {e}")
        else:
            logger.debug(f"Fichier d'optimisation non trouvé : '{file_path}'")
        return []

    def _load_general_optimizations(self):
        """Loads general server (SERVER.txt) and event (EVENTS.txt) optimizations."""
        if not self.optimization_base_path or not self.optimization_base_path.is_dir():
            logger.debug(
                "Le chemin des fichiers d'optimisation n'est pas défini ou n'est pas un répertoire. Aucune optimisation générale ne sera chargée."
            )
            return

        server_file_path = self.optimization_base_path / "SERVER.txt"
        self.server_optimizations = self._parse_optimization_file(server_file_path)
        if self.server_optimizations:
            logger.info(f"Optimisations serveur chargées depuis : {server_file_path}")

        events_file_path = self.optimization_base_path / "EVENTS.txt"
        self.event_optimizations = self._parse_optimization_file(events_file_path)
        if self.event_optimizations:
            logger.info(f"Optimisations événements chargées depuis : {events_file_path}")

    def load_all_contexts(self, log_filename: str, directory_mode_active: bool):
        """
        Determines the context folder path and loads all context files (DDL, CONFIG, PROJECT)
        and general optimization files (SERVER.txt, EVENTS.txt).
        """
        # Determine the base path for context files
        context_base_path = None
        if self.context_folder_cli_arg:  # If --context-folder is explicitly provided
            context_base_path = Path(self.context_folder_cli_arg)
            logger.info(f"Using specified context folder: {context_base_path}")
        elif log_filename:  # Determine default context folder if log_filename is provided
            if directory_mode_active:
                context_base_path = Path(log_filename) / "CONTEXT"
                logger.info(f"Using default context folder for directory mode: {context_base_path}")
            else:
                context_base_path = Path(log_filename).parent / "CONTEXT"
                logger.info(f"Using default context folder for single file mode: {context_base_path}")
        else:
            logger.warning(
                "No log file specified, cannot determine default context folder. No optimization context will be loaded."
            )

        self.optimization_base_path = context_base_path

        # Validate and load contexts if path exists and is a directory
        if self.optimization_base_path:
            if not self.optimization_base_path.exists():
                logger.warning(
                    f"Le chemin spécifié pour le dossier de contexte n'existe pas : {self.optimization_base_path}. Aucune optimisation ni fichier de contexte ne sera chargé."
                )
                self.optimization_base_path = None  # Clear it if it doesn't exist
            elif not self.optimization_base_path.is_dir():
                logger.warning(
                    f"Le chemin spécifié pour le dossier de contexte n'est pas un répertoire : {self.optimization_base_path}. Les optimisations et fichiers de contexte ne seront pas chargés."
                )
                self.optimization_base_path = None  # Clear it if it's not a directory
            else:
                self._load_general_optimizations()

                # Load DDL.txt, CONFIG.txt, and PROJECT.txt from the context folder
                # These context files are now optional.
                self.ddl_context = self._load_file_content(
                    self.optimization_base_path / "DDL.txt", "DDL context", required=False
                )
                self.server_configuration_context = self._load_file_content(
                    self.optimization_base_path / "CONFIG.txt", "Server configuration context", required=False
                )
                self.project_context = self._load_file_content(
                    self.optimization_base_path / "PROJECT.txt", "Project context", required=False
                )

    def get_query_optimizations(
        self,
        query_code: str,
    ):
        """Retrieves or loads query-specific optimizations for a given query code."""

        if not self.optimization_base_path or not self.optimization_base_path.is_dir():
            return []

        if query_code not in self.query_optimizations_cache:
            query_folder_path = self.optimization_base_path / "QUERIES"
            file_path = query_folder_path / f"{query_code[:6]}.txt"
            self.query_optimizations_cache[query_code] = self._parse_optimization_file(file_path)
            if self.query_optimizations_cache[query_code]:
                logger.info(f"Optimisations de requête chargées pour {query_code[:6]} depuis : {file_path}")

        return self.query_optimizations_cache.get(query_code, [])

    def build_full_prompt_with_optimizations(
        self, plan: str, query_code: str, custom_prompt: str = None, lang: str = "en"
    ) -> str:
        """
        Constructs the full prompt for AI analysis by combining system/format prompts,
        the main analysis prompt, various contexts, applied optimizations, custom prompts,
        and the execution plan.
        """
        prompt_segments = self.build_prompt_segments_with_optimizations(
            plan=plan,
            query_code=query_code,
            custom_prompt=custom_prompt,
            lang=lang,
        )
        full_prompt = prompt_segments["cacheable_prefix"] + prompt_segments["dynamic_suffix"]

        # DEBUG – log the complete prompt that will be sent to the AI provider
        logger.debug("Full prompt built for query %s:\n%s", query_code, full_prompt)

        return full_prompt

    def build_prompt_segments_with_optimizations(
        self, plan: str, query_code: str, custom_prompt: str = None, lang: str = "en"
    ) -> dict[str, str]:
        """Build a stable cacheable prefix and a dynamic suffix for provider-side prompt caching."""
        cacheable_prefix = ""

        # Add System and Format prompts with tags
        if self.system_prompt:
            cacheable_prefix += f">>> SYSTEM\n{self.system_prompt}\n<<< SYSTEM\n\n"
        if self.format_prompt:
            cacheable_prefix += f">>> FORMAT\n{self.format_prompt}\n<<< FORMAT\n\n"

        # Add the main plan analysis prompt content

        # Add DDL, server config, and project context with tags
        if self.ddl_context:
            cacheable_prefix += f">>> DDL\n{self.ddl_context}\n<<< DDL\n\n"
        if self.server_configuration_context:
            cacheable_prefix += (
                f">>> SERVER CONFIGURATION\n{self.server_configuration_context}\n<<< SERVER CONFIGURATION\n\n"
            )
        if self.project_context:
            cacheable_prefix += f">>> PROJECT\n{self.project_context}\n<<< PROJECT\n\n"

        # Keep server-wide context in the cacheable prefix and move query-specific context
        # into the dynamic suffix so provider-side caching can be reused across queries.
        server_applied_optimizations_context = ""
        query_applied_optimizations_context = ""
        current_query_opts = self.get_query_optimizations(query_code)
        if self.server_optimizations:
            server_applied_optimizations_context += "The following server-wide optimizations have already been applied:\n"
            for opt in self.server_optimizations:
                server_applied_optimizations_context += f"  - {opt['date']}: {opt['text']}\n"
            server_applied_optimizations_context += "\n"

        if current_query_opts:
            query_applied_optimizations_context += (
                "The following query-specific optimizations have already been applied to this query:\n"
            )
            for opt in current_query_opts:
                query_applied_optimizations_context += f"  - {opt['date']}: {opt['text']}\n"
            query_applied_optimizations_context += "\n"

        # Combine stable optimizations and custom prompt inside the cacheable prefix.
        full_custom_prompt = custom_prompt if custom_prompt else ""
        if server_applied_optimizations_context:
            full_custom_prompt = server_applied_optimizations_context + (
                f"\n{full_custom_prompt}" if full_custom_prompt else ""
            )

        # Add combined stable instructions with tags.
        if full_custom_prompt:
            cacheable_prefix += f">>> SERVER OPTIMIZATIONS\n{full_custom_prompt}\n<<< SERVER OPTIMIZATIONS\n\n"

        dynamic_suffix = ""
        if query_applied_optimizations_context:
            dynamic_suffix += (
                f">>> QUERY OPTIMIZATIONS\n{query_applied_optimizations_context}<<< QUERY OPTIMIZATIONS\n\n"
            )
        dynamic_suffix += f"{plan}\n\nPlease provide the analysis in {lang}."
        return {"cacheable_prefix": cacheable_prefix, "dynamic_suffix": dynamic_suffix}
