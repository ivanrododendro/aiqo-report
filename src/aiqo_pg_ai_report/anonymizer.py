import hashlib
import json
import logging
import re

logger = logging.getLogger(__name__)

try:
    import sqlglot
    import sqlglot.expressions as exp

    _SQLGLOT_AVAILABLE = True
except ImportError:
    _SQLGLOT_AVAILABLE = False

_BUILTIN_PG_FUNCTIONS = frozenset({
    "count", "sum", "avg", "max", "min", "array_agg", "json_agg", "jsonb_agg",
    "string_agg", "bool_and", "bool_or", "bit_and", "bit_or", "every",
    "xml_agg", "mode", "percentile_cont", "percentile_disc",
    "row_number", "rank", "dense_rank", "percent_rank", "cume_dist",
    "ntile", "lag", "lead", "first_value", "last_value", "nth_value",
    "lower", "upper", "initcap", "trim", "ltrim", "rtrim", "btrim",
    "lpad", "rpad", "length", "char_length", "bit_length", "octet_length",
    "position", "strpos", "substr", "substring", "left", "right",
    "repeat", "replace", "reverse", "split_part", "translate",
    "concat", "concat_ws", "format", "quote_ident", "quote_literal",
    "regexp_match", "regexp_matches", "regexp_replace", "regexp_split_to_array",
    "regexp_split_to_table", "to_hex", "ascii", "chr", "encode", "decode",
    "md5", "sha256", "sha512",
    "abs", "ceil", "ceiling", "floor", "round", "trunc", "sign",
    "mod", "power", "sqrt", "cbrt", "exp", "ln", "log",
    "random", "setseed", "pi",
    "now", "current_date", "current_time", "current_timestamp",
    "localtime", "localtimestamp", "clock_timestamp", "statement_timestamp",
    "transaction_timestamp", "timeofday",
    "age", "date_part", "date_trunc", "extract", "isfinite",
    "make_date", "make_interval", "make_time", "make_timestamp", "make_timestamptz",
    "to_date", "to_timestamp", "to_char", "to_number", "cast",
    "json_build_array", "json_build_object", "json_object",
    "jsonb_build_array", "jsonb_build_object", "jsonb_object",
    "json_extract_path", "jsonb_extract_path",
    "json_extract_path_text", "jsonb_extract_path_text",
    "json_array_elements", "jsonb_array_elements",
    "json_object_keys", "jsonb_object_keys",
    "json_populate_record", "jsonb_populate_record",
    "json_set", "jsonb_set", "jsonb_insert",
    "row_to_json", "to_json", "to_jsonb",
    "array_append", "array_cat", "array_dims", "array_fill",
    "array_length", "array_lower", "array_ndims", "array_position",
    "array_positions", "array_prepend", "array_remove", "array_replace",
    "array_to_string", "array_upper", "cardinality",
    "string_to_array", "unnest",
    "nextval", "currval", "lastval", "setval",
    "coalesce", "nullif", "greatest", "least",
    "current_user", "session_user", "current_database", "current_schema",
    "current_schemas", "current_setting", "set_config",
    "pg_sleep", "pg_cancel_backend", "pg_terminate_backend",
    "pg_size_pretty", "pg_relation_size", "pg_table_size",
    "pg_indexes_size", "pg_database_size",
    "pg_advisory_lock", "pg_advisory_unlock",
    "pg_try_advisory_lock", "pg_try_advisory_unlock",
    "generate_series", "generate_subscripts",
    "to_tsvector", "to_tsquery", "plainto_tsquery", "phraseto_tsquery",
    "websearch_to_tsquery", "ts_rank", "ts_rank_cd", "ts_headline",
    "overlay", "exists", "any", "all", "some",
})

_SYSTEM_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast", "pg_temp"})

_PREFIXES = {
    "table": "tbl_",
    "schema": "sch_",
    "index": "idx_",
    "column": "col_",
    "function": "fn_",
}

# Text plan node patterns: (regex, groups) where groups is a list of (group_index, kind)
_TEXT_PLAN_PATTERNS = [
    (re.compile(r'\bSeq Scan on (\w+)'), [(1, "table")]),
    (re.compile(r'\bBitmap Heap Scan on (\w+)'), [(1, "table")]),
    (re.compile(r'\bCustom Scan\b.*?\bon (\w+)'), [(1, "table")]),
    (re.compile(r'\bFunction Scan on (\w+)'), [(1, "function")]),
    (re.compile(r'\bIndex(?:\s+Only)?\s+Scan\s+using\s+(\w+)\s+on\s+(\w+)'), [(1, "index"), (2, "table")]),
    (re.compile(r'\bBitmap Index Scan on (\w+)'), [(1, "index")]),
]


class SchemaAnonymizer:
    """
    Anonymizes PostgreSQL DB object names (tables, schemas, indexes, columns, functions)
    before sending data to AI, then reverses the mapping in the AI response.

    The mapping is deterministic: sha256(name.lower())[:6] ensures the same alias
    is produced for the same name across multiple runs without any persistence.
    """

    def __init__(self) -> None:
        self._map: dict[str, str] = {}     # lowercase_real → alias
        self._reverse: dict[str, str] = {} # alias → original_real (original casing)

    def _alias(self, real: str, kind: str) -> str:
        key = real.lower()
        if key not in self._map:
            h = hashlib.sha256(key.encode()).hexdigest()[:6]
            alias = f"{_PREFIXES[kind]}{h}"
            self._map[key] = alias
            self._reverse[alias] = real
        return self._map[key]

    def extract_from_sql(self, sql: str) -> None:
        """Extract DB object names from SQL via sqlglot AST and register them in the map."""
        if not _SQLGLOT_AVAILABLE or not sql:
            return
        logger.info("Anonymizer: extracting DB object names from SQL (%d chars)", len(sql))
        before = len(self._map)
        try:
            tree = sqlglot.parse_one(sql, dialect="postgres", error_level=sqlglot.ErrorLevel.IGNORE)
        except Exception:
            return
        for node in tree.walk():
            if isinstance(node, exp.Table):
                if node.name:
                    self._alias(node.name, "table")
                if node.db and node.db.lower() not in _SYSTEM_SCHEMAS:
                    self._alias(node.db, "schema")
            elif isinstance(node, exp.Column):
                if node.name:
                    self._alias(node.name, "column")
            elif isinstance(node, exp.Index):
                if node.name:
                    self._alias(node.name, "index")
            elif isinstance(node, exp.Anonymous):
                if node.name and node.name.lower() not in _BUILTIN_PG_FUNCTIONS:
                    self._alias(node.name, "function")
        added = len(self._map) - before
        logger.debug("Anonymizer extract_from_sql: %d new entries (+%d), total %d", added, added, len(self._map))

    def extract_from_plan_json(self, plan_json: str) -> None:
        """Extract DB object names from a JSON execution plan."""
        if not plan_json:
            return
        try:
            data = json.loads(plan_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            return
        root = data.get("Plan", data) if isinstance(data, dict) else data
        self._walk_plan_node(root)

    def _walk_plan_node(self, node: object) -> None:
        if isinstance(node, list):
            for item in node:
                self._walk_plan_node(item)
            return
        if not isinstance(node, dict):
            return
        if rel := node.get("Relation Name"):
            self._alias(rel, "table")
        if schema := node.get("Schema"):
            if schema.lower() not in _SYSTEM_SCHEMAS:
                self._alias(schema, "schema")
        if idx := node.get("Index Name"):
            self._alias(idx, "index")
        if alias := node.get("Alias"):
            # Alias is usually the same as the table name
            self._alias(alias, "table")
        if fn := node.get("Function Name"):
            if fn.lower() not in _BUILTIN_PG_FUNCTIONS:
                self._alias(fn, "function")
        for sub in node.get("Plans", []):
            self._walk_plan_node(sub)

    def extract_from_plan_text(self, plan_text: str) -> None:
        """Extract DB object names from a text-format execution plan using regex."""
        if not plan_text:
            return
        for pattern, groups in _TEXT_PLAN_PATTERNS:
            for m in pattern.finditer(plan_text):
                for group_idx, kind in groups:
                    self._alias(m.group(group_idx), kind)

    def extract_from_plan(self, plan: str) -> None:
        """Auto-detect JSON vs text plan and extract DB object names."""
        if not plan:
            return
        logger.info("Anonymizer: extracting DB object names from execution plan (%d chars)", len(plan))
        before = len(self._map)
        try:
            json.loads(plan)
            self.extract_from_plan_json(plan)
        except (json.JSONDecodeError, ValueError):
            self.extract_from_plan_text(plan)
        added = len(self._map) - before
        logger.debug("Anonymizer extract_from_plan: %d new entries (+%d), total %d", added, added, len(self._map))

    def anonymize(self, text: str) -> str:
        """
        Replace all known real DB object names with their deterministic aliases.
        Longer names are substituted first to avoid partial replacements.
        Matching is case-insensitive and word-boundary aware.
        """
        if not self._map or not text:
            return text
        logger.info("Anonymizer: anonymizing text (%d chars) with %d known DB object names", len(text), len(self._map))
        for real_lower in sorted(self._map, key=len, reverse=True):
            alias = self._map[real_lower]
            text = re.sub(
                r"(?<!\w)" + re.escape(real_lower) + r"(?!\w)",
                alias,
                text,
                flags=re.IGNORECASE,
            )
        return text

    def deanonymize(self, text: str) -> str:
        """Replace all aliases in AI-generated text back with the real DB object names."""
        if not self._reverse or not text:
            return text
        logger.info("Anonymizer: de-anonymizing text (%d chars), restoring %d DB object names", len(text), len(self._reverse))
        for alias, real in self._reverse.items():
            text = text.replace(alias, real)
        return text
