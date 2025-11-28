"""Tests for CREATE OR REPLACE VIEW functionality for regular views."""

import pytest
from django.core.management import call_command

from tests.asserts_utils import is_view_exists
from tests.decorators import roll_back_schema
from tests.fixturies import dynamic_models_cleanup  # noqa


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_view_with_use_replace_false_uses_drop_create(
    temp_migrations_dir, ReplaceViewTest
):
    """Test that view with use_replace_migration=False uses DROP+CREATE even when view exists."""
    # Create and apply initial migration
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")
    assert is_view_exists(ReplaceViewTest._meta.db_table)

    # Disable REPLACE migrations
    ReplaceViewTest.use_replace_migration = False

    # Change view definition
    ReplaceViewTest.view_definition = """
        SELECT
            3 as id,
            'no_replace' as name,
            300 as value
    """

    # Generate new migration
    call_command("makeviewmigrations", "test_app")

    # Find the second migration file
    migration_files = [
        f
        for f in temp_migrations_dir.listdir()
        if f.basename.startswith("0002_") and f.basename.endswith(".py")
    ]
    assert len(migration_files) == 1
    migration_file = migration_files[0]

    # Read migration content
    migration_content = migration_file.read()

    # Verify it uses ForwardViewMigration with use_replace=False
    assert "ForwardViewMigration" in migration_content
    assert "use_replace=False" in migration_content

    # Apply migration
    call_command("migrate", "test_app")

    # Verify updated data
    result = ReplaceViewTest.objects.get()
    assert result.id == 3
    assert result.name == "no_replace"
    assert result.value == 300


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_replace_migration_forward_and_backward(temp_migrations_dir, ReplaceViewTest):
    """Test that REPLACE migrations can be applied and rolled back correctly."""
    # Create and apply initial migration
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    # Verify initial data
    result = ReplaceViewTest.objects.get()
    assert result.name == "original"
    original_value = result.value

    # Change view definition
    ReplaceViewTest.view_definition = """
        SELECT
            4 as id,
            'forward_test' as name,
            400 as value
    """

    # Generate and apply new migration
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    # Verify forward migration worked
    result = ReplaceViewTest.objects.get()
    assert result.name == "forward_test"
    assert result.value == 400

    # Rollback migration
    call_command("migrate", "test_app", "0001")

    # Verify rollback worked - should have original data
    result = ReplaceViewTest.objects.get()
    assert result.name == "original"
    assert result.value == original_value


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_replace_handles_view_not_exist_on_rollback(
    temp_migrations_dir, ReplaceViewTest
):
    """Test that backward REPLACE migration handles case where view doesn't exist."""
    # Create initial migration (view creation)
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")

    # Change view definition
    ReplaceViewTest.view_definition = """
        SELECT
            5 as id,
            'rollback_test' as name,
            500 as value
    """

    # Generate new migration
    call_command("makeviewmigrations", "test_app")

    # Apply forward migration
    call_command("migrate", "test_app")
    assert is_view_exists(ReplaceViewTest._meta.db_table)

    # Rollback to zero (no migrations)
    call_command("migrate", "test_app", "zero")

    # Verify view is dropped
    assert not is_view_exists(ReplaceViewTest._meta.db_table)


@pytest.mark.django_db(transaction=True)
@roll_back_schema
def test_materialized_view_never_uses_replace(
    temp_migrations_dir, SimpleMaterializedViewWithoutDependencies
):
    """Test that materialized views always use DROP+CREATE, never REPLACE."""
    # Create and apply initial migration
    call_command("makeviewmigrations", "test_app")
    call_command("migrate", "test_app")
    assert is_view_exists(SimpleMaterializedViewWithoutDependencies._meta.db_table)

    # Change materialized view definition
    SimpleMaterializedViewWithoutDependencies.view_definition = """
        SELECT * FROM (values (NOW() + INTERVAL '1 hour')) A(current_date_time)
    """

    # Generate new migration
    call_command("makeviewmigrations", "test_app")

    # Find the second migration file
    migration_files = [
        f
        for f in temp_migrations_dir.listdir()
        if f.basename.startswith("0002_") and f.basename.endswith(".py")
    ]
    assert len(migration_files) == 1
    migration_file = migration_files[0]

    # Read migration content
    migration_content = migration_file.read()

    # Verify it uses ForwardMaterializedViewMigration (always DROP+CREATE)
    # Materialized views inherit from ForwardViewMigrationBase with REPLACE_COMMAND_TEMPLATE=None
    assert "ForwardMaterializedViewMigration" in migration_content
    assert "BackwardMaterializedViewMigration" in migration_content

    # Apply migration
    call_command("migrate", "test_app")
    assert is_view_exists(SimpleMaterializedViewWithoutDependencies._meta.db_table)
