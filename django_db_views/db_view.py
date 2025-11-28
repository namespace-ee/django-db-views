import re
from typing import Union, Callable

from django.db import models, connections, DEFAULT_DB_ALIAS
from django.db.models.base import ModelBase

DBViewsRegistry = {}


class DBViewModelBase(ModelBase):
    def __new__(cls, *args, **kwargs):
        new_class = super().__new__(cls, *args, **kwargs)
        assert (
            new_class._meta.managed is False
        ), "For DB View managed must be set to false"
        if not new_class._meta.abstract:
            DBViewsRegistry[new_class._meta.db_table] = new_class
        return new_class


class DBView(models.Model, metaclass=DBViewModelBase):
    """
    Children should define:
        view_definition - define the view, can be callable or attribute (string)
        view definition can be per db engine.

    Optional attributes:
        use_replace_migration - Use CREATE OR REPLACE VIEW when view exists (default: True)
        dependencies - List of dependencies for this view
    """

    view_definition: Union[Callable, str, dict]
    dependencies: list
    use_replace_migration: bool = True  # Use CREATE OR REPLACE when view exists

    class Meta:
        managed = False
        abstract = True


class DBMaterializedView(DBView):
    use_replace_migration: bool = False  # Materialized views don't support REPLACE

    class Meta:
        managed = False
        abstract = True

    @classmethod
    def refresh(cls, using=None, concurrently=False):
        """
        concurrently option requires an index and postgres db
        """
        using = using or DEFAULT_DB_ALIAS
        with connections[using].cursor() as cursor:
            if concurrently:
                cursor.execute(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY %s;" % cls._meta.db_table
                )
            else:
                cursor.execute("REFRESH MATERIALIZED VIEW %s;" % cls._meta.db_table)

    @classmethod
    def get_migration_indexes(cls, using=None):
        """
        Get indexes that should be managed in migrations for this materialized view.

        This method queries the database to detect all existing indexes on the materialized view.
        Override this method in subclasses to customize which indexes are managed in migrations.

        Args:
            using: Database alias to use for querying indexes (default: DEFAULT_DB_ALIAS)

        Returns:
            dict: Mapping of index name to index definition dict with keys:
                - columns: str - Column names or expression for the index
                - unique: bool - Whether this is a unique index
                - method: str - Index method (btree, hash, gin, gist, etc.)
                - where_clause: str | None - WHERE clause for partial indexes

        Example:
            {
                "my_view_idx": {
                    "columns": "column1, column2",
                    "unique": False,
                    "method": "btree",
                    "where_clause": None
                }
            }

        Example override:
            @classmethod
            def get_migration_indexes(cls, using=None):
                indexes = super().get_migration_indexes(using)
                # Remove an index that shouldn't be managed
                indexes.pop("system_generated_idx", None)
                # Add a custom index definition
                indexes["custom_idx"] = {
                    "columns": "custom_column",
                    "unique": True,
                    "method": "btree",
                    "where_clause": None
                }
                return indexes
        """
        using = using or DEFAULT_DB_ALIAS
        indexes = {}

        with connections[using].cursor() as cursor:
            # Query PostgreSQL system catalogs to get all indexes on this materialized view
            cursor.execute(
                """
                SELECT
                    i.indexname AS index_name,
                    pg_get_indexdef(idx.indexrelid) AS index_definition,
                    idx.indisunique AS is_unique,
                    am.amname AS index_method
                FROM
                    pg_indexes i
                    JOIN pg_class c ON c.relname = i.tablename
                    JOIN pg_index idx ON idx.indrelid = c.oid
                    JOIN pg_class ic ON ic.oid = idx.indexrelid AND ic.relname = i.indexname
                    JOIN pg_am am ON am.oid = ic.relam
                WHERE
                    i.schemaname = 'public'
                    AND i.tablename = %s
                ORDER BY
                    i.indexname
                """,
                [cls._meta.db_table],
            )

            for row in cursor.fetchall():
                index_name, index_def, is_unique, index_method = row

                # Parse the index definition to extract column list
                # Example: CREATE UNIQUE INDEX idx_name ON table_name USING btree (col1, col2)
                # We need to extract "col1, col2" from this
                match = re.search(
                    r"USING\s+\w+\s+\(([^)]+)\)(?:\s+WHERE\s+(.*))?$", index_def
                )
                if match:
                    columns = match.group(1)
                    where_clause = match.group(2) if match.group(2) else None
                else:
                    # Fallback: just use the full definition
                    columns = index_def
                    where_clause = None

                indexes[index_name] = {
                    "columns": columns,
                    "unique": is_unique,
                    "method": index_method,
                    "where_clause": where_clause,
                }

        return indexes
