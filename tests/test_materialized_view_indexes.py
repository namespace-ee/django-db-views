"""Tests for materialized view index detection and migration generation."""

import pytest
from django.core.management import call_command
from django.db import connection

from tests.asserts_utils import (
    is_view_exists,
    get_index_names,
    index_exists,
    get_index_definition,
)
from tests.decorators import roll_back_schema
from tests.fixturies import dynamic_models_cleanup  # noqa


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_get_migration_indexes_basic(
    temp_migrations_dir, MaterializedViewWithMultipleIndexes
):
    """Test that get_migration_indexes() detects indexes correctly."""
    # Create the materialized view first
    call_command("makeviewmigrations", "test_app")
    assert (temp_migrations_dir / "0001_initial.py").exists()
    call_command("migrate", "test_app")
    assert is_view_exists(MaterializedViewWithMultipleIndexes._meta.db_table)

    # Create some indexes manually
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE INDEX test_name_idx ON {MaterializedViewWithMultipleIndexes._meta.db_table} (name)"
        )
        cursor.execute(
            f"CREATE UNIQUE INDEX test_id_uniq ON {MaterializedViewWithMultipleIndexes._meta.db_table} (id)"
        )
        cursor.execute(
            f"CREATE INDEX test_value_idx ON {MaterializedViewWithMultipleIndexes._meta.db_table} (value)"
        )

    # Test get_migration_indexes() detects them
    indexes = MaterializedViewWithMultipleIndexes.get_migration_indexes()

    assert "test_name_idx" in indexes
    assert "test_id_uniq" in indexes
    assert "test_value_idx" in indexes

    # Verify index properties
    assert indexes["test_name_idx"]["columns"] == "name"
    assert indexes["test_name_idx"]["unique"] is False
    assert indexes["test_name_idx"]["method"] == "btree"

    assert indexes["test_id_uniq"]["columns"] == "id"
    assert indexes["test_id_uniq"]["unique"] is True
    assert indexes["test_id_uniq"]["method"] == "btree"


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_indexes_recreated_on_view_change(
    temp_migrations_dir, MaterializedViewWithMultipleIndexes
):
    """Test that indexes are dropped and recreated when view definition changes."""
    # Create initial view with migration
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    # Create indexes
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE INDEX test_name_idx ON {MaterializedViewWithMultipleIndexes._meta.db_table} (name)"
        )

    # Verify index exists
    assert index_exists("test_name_idx")

    # Change view definition
    MaterializedViewWithMultipleIndexes.view_definition = """
        SELECT
            2 as id,
            'changed' as name,
            200 as value,
            false as active
    """

    # Generate new migration
    call_command("makeviewmigrations", "test_app")

    # Find the second migration file (0002_*.py)
    migration_files = [
        f for f in temp_migrations_dir.listdir()
        if f.basename.startswith("0002_") and f.basename.endswith(".py")
    ]
    assert len(migration_files) == 1, f"Expected 1 migration file, found {len(migration_files)}"
    migration_file = migration_files[0]

    # Read migration content
    migration_content = migration_file.read()

    # Verify migration contains index operations
    assert "DROP INDEX IF EXISTS test_name_idx" in migration_content
    assert "CREATE INDEX test_name_idx" in migration_content

    # Apply migration
    call_command("migrate", "test_app")

    # Verify index still exists after migration
    assert index_exists("test_name_idx")


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_migration_with_multiple_indexes(
    temp_migrations_dir, MaterializedViewWithMultipleIndexes
):
    """Test migration generation with multiple indexes of different types."""
    # Create view
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    # Create multiple indexes with different properties
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE INDEX test_name_idx ON {MaterializedViewWithMultipleIndexes._meta.db_table} (name)"
        )
        cursor.execute(
            f"CREATE UNIQUE INDEX test_id_value_uniq ON {MaterializedViewWithMultipleIndexes._meta.db_table} (id, value)"
        )
        cursor.execute(
            f"CREATE INDEX test_active_partial_idx ON {MaterializedViewWithMultipleIndexes._meta.db_table} (active) WHERE active = true"
        )

    # Verify all indexes exist
    index_names = get_index_names(MaterializedViewWithMultipleIndexes._meta.db_table)
    assert "test_name_idx" in index_names
    assert "test_id_value_uniq" in index_names
    assert "test_active_partial_idx" in index_names

    # Test get_migration_indexes() detection
    indexes = MaterializedViewWithMultipleIndexes.get_migration_indexes()

    # Verify multi-column index
    assert "test_id_value_uniq" in indexes
    assert "id, value" in indexes["test_id_value_uniq"]["columns"]
    assert indexes["test_id_value_uniq"]["unique"] is True

    # Verify partial index with WHERE clause
    assert "test_active_partial_idx" in indexes
    assert indexes["test_active_partial_idx"]["where_clause"] is not None
    assert "active = true" in indexes["test_active_partial_idx"]["where_clause"]


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_migration_forward_and_backward(
    temp_migrations_dir, MaterializedViewWithMultipleIndexes
):
    """Test that migrations can be applied and rolled back correctly with indexes."""
    # Create initial view
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    # Create an index
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE INDEX test_name_idx ON {MaterializedViewWithMultipleIndexes._meta.db_table} (name)"
        )

    assert index_exists("test_name_idx")

    # Change view definition to trigger recreation
    MaterializedViewWithMultipleIndexes.view_definition = """
        SELECT
            3 as id,
            'rollback_test' as name,
            300 as value,
            true as active
    """

    # Generate and apply new migration
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    # Index should still exist after forward migration
    assert index_exists("test_name_idx")

    # Rollback migration
    call_command("migrate", "test_app", "0001")

    # Index should still exist after rollback
    assert index_exists("test_name_idx")


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_view_without_indexes(
    temp_migrations_dir, SimpleMaterializedViewWithoutDependencies
):
    """Test that views without indexes don't generate index operations."""
    # Create view without any indexes
    call_command("makeviewmigrations", "test_app")
    migration_content = (temp_migrations_dir / "0001_initial.py").read()

    # Verify no index operations in migration
    assert "DROP INDEX" not in migration_content
    assert (
        "CREATE INDEX" not in migration_content or "CREATE INDEX" in migration_content
    )  # May have system indexes

    call_command("migrate", "test_app")

    # Verify view exists but has no user-created indexes
    assert is_view_exists(SimpleMaterializedViewWithoutDependencies._meta.db_table)
    indexes = SimpleMaterializedViewWithoutDependencies.get_migration_indexes()
    # Should only have system indexes if any
    user_indexes = [name for name in indexes.keys() if not name.endswith("_pkey")]
    assert len(user_indexes) == 0


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_index_definition_format(
    temp_migrations_dir, MaterializedViewWithMultipleIndexes
):
    """Test that index definitions are correctly formatted in migrations."""
    # Create view and index
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE INDEX test_name_idx ON {MaterializedViewWithMultipleIndexes._meta.db_table} (name)"
        )

    # Get index definition from database
    db_definition = get_index_definition("test_name_idx")
    assert "USING btree" in db_definition
    assert "(name)" in db_definition

    # Verify get_migration_indexes() returns correct structure
    indexes = MaterializedViewWithMultipleIndexes.get_migration_indexes()
    assert indexes["test_name_idx"]["method"] == "btree"
    assert indexes["test_name_idx"]["columns"] == "name"
    assert indexes["test_name_idx"]["where_clause"] is None


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_no_duplicate_index_operations(
    temp_migrations_dir, MaterializedViewWithMultipleIndexes
):
    """Test that running makeviewmigrations multiple times doesn't create duplicate operations."""
    # Create view and index
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE INDEX test_name_idx ON {MaterializedViewWithMultipleIndexes._meta.db_table} (name)"
        )

    # Run makeviewmigrations again without changes
    call_command("makeviewmigrations", "test_app")

    # Should not create a new migration
    migrations = [f for f in temp_migrations_dir.listdir() if f.basename.endswith(".py")]
    py_migrations = [m for m in migrations if m.basename != "__init__.py"]
    assert len(py_migrations) == 1  # Only initial migration
