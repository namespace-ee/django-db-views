from django.db import connections


def is_table_exists(table_name: str, using: str = "default") -> bool:
    with connections[using].cursor() as cursor:
        return table_name in connections[using].introspection.table_names(cursor)


def is_view_exists(view_name: str, using: str = "default") -> bool:
    with connections[using].cursor() as cursor:
        views = [
            table.name
            for table in connections[using].introspection.get_table_list(cursor)
            if table.type == "v"
        ]
        return view_name.split('"."')[-1] in views


def get_index_names(table_name: str, using: str = "default") -> list[str]:
    """Get all index names for a given table."""
    with connections[using].cursor() as cursor:
        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = %s
            ORDER BY indexname
            """,
            [table_name],
        )
        return [row[0] for row in cursor.fetchall()]


def index_exists(index_name: str, using: str = "default") -> bool:
    """Check if a specific index exists."""
    with connections[using].cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = %s
            """,
            [index_name],
        )
        return cursor.fetchone()[0] > 0


def get_index_definition(index_name: str, using: str = "default") -> str:
    """Get the full index definition from the database."""
    with connections[using].cursor() as cursor:
        cursor.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = %s
            """,
            [index_name],
        )
        row = cursor.fetchone()
        return row[0] if row else None
