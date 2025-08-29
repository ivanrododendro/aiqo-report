import hashlib
import re

import sqlparse


class SQLUtils:
    @staticmethod
    def normalize_sql(sql):
        # Formater le SQL avec sqlparse
        formatted_sql = sqlparse.format(sql, strip_comments=True, reindent=True, strip_whitespace=True)

        # Remplacer les constantes numériques et les chaînes de caractères par '?'
        formatted_sql = re.sub(r"\b\d+\b", "?", formatted_sql)  # Nombres
        formatted_sql = re.sub(r"'[^']*'", "?", formatted_sql)  # Chaînes de caractères

        return formatted_sql

    @staticmethod
    def get_query_code(query):
        normalized_query = SQLUtils.normalize_sql(query)
        value_str = str(normalized_query).encode("utf-8")
        return hashlib.sha256(value_str).hexdigest().upper()
