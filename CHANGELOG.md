# Changelog
Changelogs starts from version 0.1.3

## Unreleased

## Released

### [0.1.15]
- Add CREATE OR REPLACE VIEW support for regular views (PostgreSQL, MySQL)
  - Atomic view updates that preserve dependencies, permissions, and ownership
  - Auto-detection based on database engine (PostgreSQL/MySQL use CREATE OR REPLACE, SQLite uses DROP+CREATE)
  - Add `use_replace_migration` attribute to control behavior per view model
  - Runtime decision making for multi-database views with different engines
- Add automatic index management for materialized views
  - Indexes on materialized views are now detected and included in migrations
  - Support for unique, partial (with WHERE clause), and multi-column indexes
  - Add `get_migration_indexes()` method to `DBMaterializedView` for customization
  - Automatic index recreation when view definition changes

### [0.1.14]
- Add ability to set custom dependencies, to cover what is required by query definition

### [0.1.13]
- Fix dependency issue (on psycopg) introduced in 0.1.12.

### [0.1.12]
- quote view names at migrations as django does with table names.

### [0.1.11]
- use sqlparse to detect view changes

### [0.1.10]
- fix no_migrations_teardown at django_db_views_setup fixture

### [0.1.9]
- Add pytest `--no-migrations` support

### [0.1.8]
- Sqlmigrate command shows sql definitions of a view models

### [0.1.7]
- Support for reading ViewRunPython operations from SeparateDatabaseAndState operations

### [0.1.6]
- Adjusted tests to django 4.2

### [0.1.5]
- Fix view_migration_context
- Fix function that generate table hash name, to return lower case strings always 

### [0.1.4]
- Fix broken migration from 0.1.3 version.  https://github.com/BezBartek/django-db-views/issues/20


### [0.1.3]
- Detect and delete removed views or views implementations for specified engines.
- Materialized Views
- Started using project state to track models (Operations defines state_forwards)
- Added view registry to simplify tracking of model changes

### [0.1.2]
- Change log starts from 0.1.3
