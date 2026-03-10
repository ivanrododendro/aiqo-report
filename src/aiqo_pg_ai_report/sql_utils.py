import hashlib
import re
import unicodedata

import sqlparse


class SQLUtils:
    _STRING_LITERAL_RE = re.compile(r"(?:E)?'(?:''|[^'])*'")
    _DOLLAR_QUOTED_RE = re.compile(r"\$[^$]*\$.*?\$[^$]*\$", re.DOTALL)
    _NUMERIC_LITERAL_RE = re.compile(r"(?<![\w$])[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?(?![\w$])")
    _WHITESPACE_RE = re.compile(r"\s+")

    @staticmethod
    def normalize_sql(sql):
        normalized_sql = unicodedata.normalize("NFKC", sql or "")
        normalized_sql = normalized_sql.replace("\r\n", "\n").replace("\r", "\n")

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
