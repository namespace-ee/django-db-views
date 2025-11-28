from typing import TypeVar

from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps
from django.utils.deconstruct import deconstructible


DatabaseSchemaEditor = TypeVar("DatabaseSchemaEditor", bound=BaseDatabaseSchemaEditor)


class ViewMigration(object):
    DROP_COMMAND_TEMPLATE: str
    CREATE_COMMAND_TEMPLATE: str
    REPLACE_COMMAND_TEMPLATE: str

    def __init__(
        self,
        view_definition: str,
        table_name: str,
        engine=None,
        use_replace: bool = True,
    ):
        # if provided engine is None, then we are assuming that engine is same as db engine.
        # We do that to keep backward compatibility.
        self.view_engine = engine
        self.view_definition = view_definition
        self.table_name = table_name
        self.use_replace = use_replace

    def _should_use_replace(self, engine: str) -> bool:
        """
        Determine if CREATE OR REPLACE should be used based on template availability,
        user preference, and engine support.

        Args:
            engine: Database engine string (e.g., 'django.db.backends.postgresql')

        Returns:
            True if CREATE OR REPLACE should be used, False for DROP+CREATE
        """
        # If no REPLACE template defined (e.g., materialized views), can't use it
        if self.REPLACE_COMMAND_TEMPLATE is None:
            return False

        if not self.use_replace:
            # User explicitly opted out
            return False

        if "sqlite" in engine:
            # SQLite does NOT support CREATE OR REPLACE VIEW
            return False

        # For all other engines (PostgreSQL, MySQL, etc.), trust the user's preference
        # If an unknown database supports CREATE OR REPLACE, the user can enable it
        return True


class ForwardViewMigrationBase(ViewMigration):
    def __call__(self, apps: StateApps, schema_editor: DatabaseSchemaEditor):
        if self.view_definition:
            # Get the actual database engine being used
            engine = schema_editor.connection.settings_dict["ENGINE"]
            if self.view_engine is None or self.view_engine == engine:
                if self._should_use_replace(engine):
                    # Use CREATE OR REPLACE (atomic operation)
                    schema_editor.execute(
                        self.REPLACE_COMMAND_TEMPLATE
                        % (
                            schema_editor.quote_name(self.table_name),
                            self.view_definition,
                        )
                    )
                else:
                    # Use DROP + CREATE (traditional approach)
                    schema_editor.execute(
                        self.DROP_COMMAND_TEMPLATE
                        % schema_editor.quote_name(self.table_name)
                    )
                    schema_editor.execute(
                        self.CREATE_COMMAND_TEMPLATE
                        % (
                            schema_editor.quote_name(self.table_name),
                            self.view_definition,
                        )
                    )


class BackwardViewMigrationBase(ViewMigration):
    """
    Base class for backward migrations with shared CREATE OR REPLACE vs DROP+CREATE logic.
    """

    def __call__(self, apps: StateApps, schema_editor: DatabaseSchemaEditor):
        engine = schema_editor.connection.settings_dict["ENGINE"]
        if self.view_engine is None or self.view_engine == engine:
            if self.view_definition:
                if self._should_use_replace(engine):
                    # Use CREATE OR REPLACE to restore previous definition
                    schema_editor.execute(
                        self.REPLACE_COMMAND_TEMPLATE
                        % (
                            schema_editor.quote_name(self.table_name),
                            self.view_definition,
                        )
                    )
                else:
                    # Use DROP + CREATE
                    schema_editor.execute(
                        self.DROP_COMMAND_TEMPLATE
                        % schema_editor.quote_name(self.table_name)
                    )
                    schema_editor.execute(
                        self.CREATE_COMMAND_TEMPLATE
                        % (
                            schema_editor.quote_name(self.table_name),
                            self.view_definition,
                        )
                    )
            else:
                # No previous definition, just drop the view
                schema_editor.execute(
                    self.DROP_COMMAND_TEMPLATE
                    % schema_editor.quote_name(self.table_name)
                )


@deconstructible
class ForwardViewMigration(ForwardViewMigrationBase):
    """
    Forward migration for database views with runtime CREATE OR REPLACE decision.

    Decides at runtime whether to use:
    - CREATE OR REPLACE VIEW (atomic, preserves dependencies) - PostgreSQL, MySQL, etc.
    - DROP + CREATE VIEW (traditional) - SQLite or when user opts out

    Benefits of CREATE OR REPLACE:
    - Atomic operation (no moment where view doesn't exist)
    - Preserves view dependencies (dependent views, functions, triggers)
    - Maintains permissions and ownership
    - Safer for production environments
    """

    DROP_COMMAND_TEMPLATE = "DROP VIEW IF EXISTS %s;"
    CREATE_COMMAND_TEMPLATE = "CREATE VIEW %s as %s;"
    REPLACE_COMMAND_TEMPLATE = "CREATE OR REPLACE VIEW %s AS %s;"


@deconstructible
class BackwardViewMigration(BackwardViewMigrationBase):
    DROP_COMMAND_TEMPLATE = "DROP VIEW IF EXISTS %s;"
    CREATE_COMMAND_TEMPLATE = "CREATE VIEW %s as %s;"
    REPLACE_COMMAND_TEMPLATE = "CREATE OR REPLACE VIEW %s AS %s;"


@deconstructible
class ForwardMaterializedViewMigration(ForwardViewMigrationBase):
    DROP_COMMAND_TEMPLATE = "DROP MATERIALIZED VIEW IF EXISTS %s;"
    CREATE_COMMAND_TEMPLATE = "CREATE MATERIALIZED VIEW %s as %s;"
    REPLACE_COMMAND_TEMPLATE = None  # Not supported for materialized views


@deconstructible
class BackwardMaterializedViewMigration(BackwardViewMigrationBase):
    DROP_COMMAND_TEMPLATE = "DROP MATERIALIZED VIEW IF EXISTS %s;"
    CREATE_COMMAND_TEMPLATE = "CREATE MATERIALIZED VIEW %s as %s;"
    REPLACE_COMMAND_TEMPLATE = None  # Not supported for materialized views


class DropViewMigration(object):
    DROP_COMMAND_TEMPLATE: str

    def __init__(self, table_name: str, engine=None):
        self.table_name = table_name
        self.view_engine = engine

    def __call__(self, apps: StateApps, schema_editor: DatabaseSchemaEditor):
        if (
            self.view_engine is None
            or self.view_engine == schema_editor.connection.settings_dict["ENGINE"]
        ):
            schema_editor.execute(
                self.DROP_COMMAND_TEMPLATE % schema_editor.quote_name(self.table_name)
            )


@deconstructible
class DropMaterializedView(DropViewMigration):
    DROP_COMMAND_TEMPLATE = "DROP MATERIALIZED VIEW IF EXISTS %s;"


@deconstructible
class DropView(DropViewMigration):
    DROP_COMMAND_TEMPLATE = "DROP VIEW IF EXISTS %s;"
