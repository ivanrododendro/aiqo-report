import hashlib
import os
import re
import unicodedata

import sqlparse
import sqlparse.engine.grouping


class SQLUtils:
    SHORT_QUERY_CODE_LENGTH = 6
    SQLPARSE_MAX_GROUPING_TOKENS_ENV = "AIQO_SQLPARSE_MAX_GROUPING_TOKENS"
    _STRING_LITERAL_RE = re.compile(r"(?:E)?'(?:''|[^'])*'")
    _DOLLAR_QUOTED_RE = re.compile(r"\$[^$]*\$.*?\$[^$]*\$", re.DOTALL)
    _NUMERIC_LITERAL_RE = re.compile(r"(?<![\w$])[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?(?![\w$])")
    _WHITESPACE_RE = re.compile(r"\s+")
    _SHORT_QUERY_CODE_RE = re.compile(r"^[0-9A-F]{6}$")

    @staticmethod
    def _configure_sqlparse_grouping_limits() -> None:
        max_grouping_tokens = os.getenv(SQLUtils.SQLPARSE_MAX_GROUPING_TOKENS_ENV)
        if max_grouping_tokens is None:
            return

        normalized_value = max_grouping_tokens.strip().lower()
        if normalized_value == "none":
            sqlparse.engine.grouping.MAX_GROUPING_TOKENS = None
            return

        try:
            parsed_value = int(normalized_value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid {SQLUtils.SQLPARSE_MAX_GROUPING_TOKENS_ENV} value '{max_grouping_tokens}'. "
                "Expected 'none' or a positive integer."
            ) from exc

        if parsed_value <= 0:
            raise ValueError(
                f"Invalid {SQLUtils.SQLPARSE_MAX_GROUPING_TOKENS_ENV} value '{max_grouping_tokens}'. "
                "Expected 'none' or a positive integer."
            )

        sqlparse.engine.grouping.MAX_GROUPING_TOKENS = parsed_value

    @staticmethod
    def normalize_sql(sql):
        normalized_sql = unicodedata.normalize("NFKC", sql or "")
        normalized_sql = normalized_sql.replace("\r\n", "\n").replace("\r", "\n")

        SQLUtils._configure_sqlparse_grouping_limits()

        # Keep formatting deterministic and compact before hashing.
        normalized_sql = sqlparse.format(
            normalized_sql,
            strip_comments=True,
            keyword_case="lower",
            strip_whitespace=True,
            reindent=False,
        )

        normalized_sql = SQLUtils._DOLLAR_QUOTED_RE.sub("?", normalized_sql)
        normalized_sql = SQLUtils._STRING_LITERAL_RE.sub("?", normalized_sql)
        normalized_sql = SQLUtils._NUMERIC_LITERAL_RE.sub("?", normalized_sql)
        normalized_sql = SQLUtils._WHITESPACE_RE.sub(" ", normalized_sql).strip().rstrip(";").strip()

        return normalized_sql

    @staticmethod
    def get_query_code(query):
        normalized_query = SQLUtils.normalize_sql(query)
        value_str = str(normalized_query).encode("utf-8")
        return hashlib.sha256(value_str).hexdigest().upper()

    @staticmethod
    def get_short_query_code(query: str) -> str:
        return SQLUtils.get_query_code(query)[: SQLUtils.SHORT_QUERY_CODE_LENGTH]

    @staticmethod
    def normalize_short_query_code(value: str) -> str:
        normalized_value = (value or "").strip().upper()
        if not SQLUtils._SHORT_QUERY_CODE_RE.fullmatch(normalized_value):
            raise ValueError(
                f"Invalid target query filter '{value}'. Expected exactly {SQLUtils.SHORT_QUERY_CODE_LENGTH} hexadecimal characters."
            )
        return normalized_value
