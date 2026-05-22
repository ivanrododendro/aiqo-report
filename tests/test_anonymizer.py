import json
import pytest

from aiqo_pg_ai_report.anonymizer import SchemaAnonymizer, _SQLGLOT_AVAILABLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_anon() -> SchemaAnonymizer:
    return SchemaAnonymizer()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_name_same_alias_across_instances(self):
        a1 = make_anon()
        a2 = make_anon()
        a1._alias("users", "table")
        a2._alias("users", "table")
        assert a1._map["users"] == a2._map["users"]

    def test_same_name_same_alias_case_insensitive(self):
        a = make_anon()
        alias_lower = a._alias("orders", "table")
        alias_upper = a._alias("ORDERS", "table")
        assert alias_lower == alias_upper

    def test_different_names_different_aliases(self):
        a = make_anon()
        t1 = a._alias("users", "table")
        t2 = a._alias("orders", "table")
        assert t1 != t2

    def test_prefix_by_kind(self):
        a = make_anon()
        assert a._alias("mytable", "table").startswith("tbl_")
        assert a._alias("myschema", "schema").startswith("sch_")
        assert a._alias("myindex", "index").startswith("idx_")
        assert a._alias("mycol", "column").startswith("col_")
        assert a._alias("myfunc", "function").startswith("fn_")


# ---------------------------------------------------------------------------
# JSON plan extraction
# ---------------------------------------------------------------------------

class TestExtractFromPlanJson:
    def _plan(self, **kwargs) -> str:
        return json.dumps({"Plan": kwargs})

    def test_extracts_relation_name(self):
        a = make_anon()
        a.extract_from_plan_json(self._plan(**{"Node Type": "Seq Scan", "Relation Name": "orders"}))
        assert "orders" in a._map

    def test_extracts_schema(self):
        a = make_anon()
        a.extract_from_plan_json(self._plan(**{"Schema": "myschema", "Relation Name": "tbl"}))
        assert "myschema" in a._map

    def test_skips_system_schema(self):
        a = make_anon()
        a.extract_from_plan_json(self._plan(**{"Schema": "pg_catalog", "Relation Name": "pg_class"}))
        assert "pg_catalog" not in a._map

    def test_extracts_index_name(self):
        a = make_anon()
        a.extract_from_plan_json(self._plan(**{"Index Name": "idx_users_email"}))
        assert "idx_users_email" in a._map
        assert a._map["idx_users_email"].startswith("idx_")

    def test_extracts_alias(self):
        a = make_anon()
        a.extract_from_plan_json(self._plan(**{"Relation Name": "users", "Alias": "u"}))
        assert "u" in a._map

    def test_extracts_function_name(self):
        a = make_anon()
        a.extract_from_plan_json(self._plan(**{"Function Name": "my_custom_func"}))
        assert "my_custom_func" in a._map
        assert a._map["my_custom_func"].startswith("fn_")

    def test_skips_builtin_function(self):
        a = make_anon()
        a.extract_from_plan_json(self._plan(**{"Function Name": "generate_series"}))
        assert "generate_series" not in a._map

    def test_recurses_into_sub_plans(self):
        a = make_anon()
        plan = json.dumps({
            "Plan": {
                "Node Type": "Hash Join",
                "Plans": [
                    {"Node Type": "Seq Scan", "Relation Name": "users"},
                    {"Node Type": "Seq Scan", "Relation Name": "orders"},
                ]
            }
        })
        a.extract_from_plan_json(plan)
        assert "users" in a._map
        assert "orders" in a._map

    def test_invalid_json_does_not_raise(self):
        a = make_anon()
        a.extract_from_plan_json("not json at all")  # must not raise

    def test_empty_string_does_not_raise(self):
        a = make_anon()
        a.extract_from_plan_json("")


# ---------------------------------------------------------------------------
# Text plan extraction
# ---------------------------------------------------------------------------

class TestExtractFromPlanText:
    def test_seq_scan(self):
        a = make_anon()
        a.extract_from_plan_text("  ->  Seq Scan on orders  (cost=0.00..5.01 rows=1 width=8)")
        assert "orders" in a._map
        assert a._map["orders"].startswith("tbl_")

    def test_bitmap_heap_scan(self):
        a = make_anon()
        a.extract_from_plan_text("  ->  Bitmap Heap Scan on users")
        assert "users" in a._map

    def test_index_scan(self):
        a = make_anon()
        a.extract_from_plan_text("  ->  Index Scan using idx_orders_user_id on orders")
        assert "idx_orders_user_id" in a._map
        assert a._map["idx_orders_user_id"].startswith("idx_")
        assert "orders" in a._map

    def test_index_only_scan(self):
        a = make_anon()
        a.extract_from_plan_text("  ->  Index Only Scan using idx_users_email on users")
        assert "idx_users_email" in a._map
        assert "users" in a._map

    def test_bitmap_index_scan(self):
        a = make_anon()
        a.extract_from_plan_text("  ->  Bitmap Index Scan on idx_orders_status")
        assert "idx_orders_status" in a._map

    def test_empty_string_does_not_raise(self):
        a = make_anon()
        a.extract_from_plan_text("")


# ---------------------------------------------------------------------------
# SQL extraction (requires sqlglot)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _SQLGLOT_AVAILABLE, reason="sqlglot not installed")
class TestExtractFromSql:
    def test_extracts_table_names(self):
        a = make_anon()
        a.extract_from_sql("SELECT * FROM users JOIN orders ON orders.user_id = users.id")
        assert "users" in a._map
        assert "orders" in a._map
        assert a._map["users"].startswith("tbl_")

    def test_extracts_schema(self):
        a = make_anon()
        a.extract_from_sql("SELECT * FROM myschema.users")
        assert "myschema" in a._map
        assert a._map["myschema"].startswith("sch_")

    def test_skips_system_schema(self):
        a = make_anon()
        a.extract_from_sql("SELECT * FROM pg_catalog.pg_class")
        assert "pg_catalog" not in a._map

    def test_extracts_columns(self):
        a = make_anon()
        a.extract_from_sql("SELECT u.email, u.status FROM users u WHERE u.status = 'active'")
        assert "email" in a._map
        assert "status" in a._map
        assert a._map["email"].startswith("col_")

    def test_invalid_sql_does_not_raise(self):
        a = make_anon()
        a.extract_from_sql("THIS IS NOT SQL !!!")

    def test_empty_string_does_not_raise(self):
        a = make_anon()
        a.extract_from_sql("")

    def test_extracts_index_name_from_create_index(self):
        a = make_anon()
        a.extract_from_sql("CREATE INDEX idx_users_email ON public.users (email)")
        assert "idx_users_email" in a._map
        assert a._map["idx_users_email"].startswith("idx_")

    def test_create_index_extracts_table_and_schema(self):
        a = make_anon()
        a.extract_from_sql("CREATE INDEX idx_orders_customer ON public.orders (customer_id)")
        assert "idx_orders_customer" in a._map
        assert "orders" in a._map
        assert "public" in a._map

    def test_create_unique_index_extracts_index_name(self):
        a = make_anon()
        a.extract_from_sql("CREATE UNIQUE INDEX idx_users_id ON users (id)")
        assert "idx_users_id" in a._map
        assert a._map["idx_users_id"].startswith("idx_")


# ---------------------------------------------------------------------------
# Anonymize
# ---------------------------------------------------------------------------

class TestAnonymize:
    def test_replaces_table_name(self):
        a = make_anon()
        a._alias("users", "table")
        result = a.anonymize("SELECT * FROM users WHERE users.id = 1")
        assert "users" not in result
        assert a._map["users"] in result

    def test_case_insensitive_replacement(self):
        a = make_anon()
        a._alias("users", "table")
        result = a.anonymize("select * from USERS")
        assert "USERS" not in result
        assert a._map["users"] in result

    def test_word_boundary_prevents_partial_match(self):
        a = make_anon()
        a._alias("user", "table")
        # "current_user" contains "user" but must NOT be replaced
        result = a.anonymize("SELECT current_user, user_id FROM accounts")
        assert "current_user" in result
        assert "user_id" in result

    def test_longer_name_replaced_before_shorter(self):
        a = make_anon()
        a._alias("user_events", "table")
        a._alias("user", "table")
        result = a.anonymize("FROM user_events JOIN user")
        # user_events must be its own alias, not tbl_X + "_events"
        user_alias = a._map["user"]
        events_alias = a._map["user_events"]
        assert events_alias in result
        assert user_alias in result
        assert f"{user_alias}_events" not in result

    def test_empty_text_returns_empty(self):
        a = make_anon()
        a._alias("users", "table")
        assert a.anonymize("") == ""

    def test_empty_map_returns_original(self):
        a = make_anon()
        original = "SELECT * FROM users"
        assert a.anonymize(original) == original

    def test_schema_qualified_name(self):
        a = make_anon()
        a._alias("myschema", "schema")
        a._alias("orders", "table")
        result = a.anonymize("FROM myschema.orders")
        assert "myschema" not in result
        assert "orders" not in result


# ---------------------------------------------------------------------------
# Deanonymize
# ---------------------------------------------------------------------------

class TestDeanonymize:
    def test_restores_original_names(self):
        a = make_anon()
        a._alias("users", "table")
        a._alias("orders", "table")
        anon = a.anonymize("SELECT * FROM users JOIN orders ON orders.user_id = users.id")
        restored = a.deanonymize(anon)
        assert "users" in restored
        assert "orders" in restored

    def test_roundtrip_preserves_text(self):
        a = make_anon()
        a._alias("users", "table")
        a._alias("email", "column")
        original = "The users table has an index on email for fast lookups."
        roundtrip = a.deanonymize(a.anonymize(original))
        assert roundtrip == original

    def test_empty_text_returns_empty(self):
        a = make_anon()
        assert a.deanonymize("") == ""

    def test_empty_map_returns_original(self):
        a = make_anon()
        original = "some text with tbl_abc123"
        assert a.deanonymize(original) == original


# ---------------------------------------------------------------------------
# Integration: full flow
# ---------------------------------------------------------------------------

class TestFullFlow:
    def test_json_plan_anonymize_deanonymize(self):
        plan = json.dumps({
            "Plan": {
                "Node Type": "Hash Join",
                "Relation Name": "orders",
                "Schema": "billing",
                "Plans": [
                    {"Node Type": "Seq Scan", "Relation Name": "users", "Index Name": "idx_users_pk"},
                ]
            }
        })
        a = make_anon()
        a.extract_from_plan_json(plan)
        anon_plan = a.anonymize(plan)

        assert "orders" not in anon_plan
        assert "users" not in anon_plan
        assert "billing" not in anon_plan

        restored = a.deanonymize(anon_plan)
        assert "orders" in restored
        assert "users" in restored
        assert "billing" in restored

    def test_text_plan_anonymize_deanonymize(self):
        plan = (
            "Hash Join  (cost=12.05..24.58 rows=1 width=16)\n"
            "  ->  Seq Scan on customers  (cost=0.00..11.50 rows=150 width=8)\n"
            "  ->  Index Scan using idx_invoices_customer_id on invoices"
        )
        a = make_anon()
        a.extract_from_plan_text(plan)
        anon_plan = a.anonymize(plan)

        assert "customers" not in anon_plan
        assert "invoices" not in anon_plan
        assert "idx_invoices_customer_id" not in anon_plan

        restored = a.deanonymize(anon_plan)
        assert "customers" in restored
        assert "invoices" in restored
        assert "idx_invoices_customer_id" in restored

    def test_ai_response_deanonymize(self):
        a = make_anon()
        a._alias("orders", "table")
        a._alias("idx_orders_status", "index")
        orders_alias = a._map["orders"]
        idx_alias = a._map["idx_orders_status"]

        fake_ai_response = (
            f"The {orders_alias} table is scanned sequentially. "
            f"Adding {idx_alias} would improve performance."
        )
        restored = a.deanonymize(fake_ai_response)
        assert "orders" in restored
        assert "idx_orders_status" in restored
        assert orders_alias not in restored
        assert idx_alias not in restored

    def test_no_cross_contamination_between_plan_and_ai_response(self):
        a = make_anon()
        plan = json.dumps({"Plan": {"Relation Name": "payments", "Schema": "finance"}})
        a.extract_from_plan_json(plan)
        anon_plan = a.anonymize(plan)
        assert "payments" not in anon_plan
        assert "finance" not in anon_plan

        # AI response references the same tables
        ai = a.deanonymize(anon_plan)
        assert "payments" in ai
        assert "finance" in ai

    def test_consistency_same_alias_across_all_sources(self):
        """
        The same DB object name must produce identical aliases regardless of
        where it was first seen: SQL query, JSON plan, text plan, or free text.
        All sources share one map, so anonymization is coherent across the full
        prompt (query + plan + DDL/context) and the AI response is correctly
        restored.
        """
        sql = "SELECT u.email FROM public.users u WHERE u.status = 'active'"
        json_plan = json.dumps({
            "Plan": {
                "Node Type": "Seq Scan",
                "Relation Name": "users",
                "Schema": "public",
                "Index Name": "idx_users_email",
            }
        })
        text_plan = (
            "Seq Scan on users  (cost=0.00..12.50 rows=150 width=8)\n"
            "  ->  Index Scan using idx_users_email on users"
        )
        ddl_context = "CREATE TABLE public.users (email TEXT, status TEXT);"
        server_context = "Analyze users nightly to keep statistics fresh."

        a = make_anon()
        a.extract_from_sql(sql)
        a.extract_from_plan_json(json_plan)
        a.extract_from_plan_text(text_plan)
        if _SQLGLOT_AVAILABLE:
            a.extract_from_sql(ddl_context)

        # All sources must resolve to the exact same alias for each name
        users_alias = a._map["users"]
        public_alias = a._map["public"]
        idx_alias = a._map["idx_users_email"]

        anon_sql = a.anonymize(sql)
        anon_json = a.anonymize(json_plan)
        anon_text = a.anonymize(text_plan)
        anon_server = a.anonymize(server_context)

        # The alias is the same in every anonymized source
        assert users_alias in anon_sql
        assert users_alias in anon_json
        assert users_alias in anon_text
        assert users_alias in anon_server

        assert public_alias in anon_sql
        assert public_alias in anon_json

        assert idx_alias in anon_json
        assert idx_alias in anon_text

        # Real names are gone from every source
        for anon in (anon_sql, anon_json, anon_text, anon_server):
            assert "users" not in anon
            assert "public" not in anon

        # De-anonymizing the AI response (which uses the same aliases) restores real names
        fake_ai = (
            f"The {users_alias} table in schema {public_alias} is scanned sequentially. "
            f"Consider using {idx_alias} to avoid the full scan."
        )
        restored = a.deanonymize(fake_ai)
        assert "users" in restored
        assert "public" in restored
        assert "idx_users_email" in restored
        assert users_alias not in restored
        assert public_alias not in restored
        assert idx_alias not in restored
