# django-db-views


[![License](https://img.shields.io/:license-mit-blue.svg)](http://doge.mit-license.org)  
[![PyPi](https://badge.fury.io/py/django-db-views.svg)](https://pypi.org/project/django-db-views/)  
**Django Versions** 2.2 to 5.1+  
**Python Versions** 3.9 to 3.13 


### How to install?
  - `pip install django-db-views`

### What we offer
 - Database views
 - Materialized views
 - views schema migrations
 - indexing for materialized views
 - database table function (future)

### How to use?
   - add `django_db_views` to `INSTALLED_APPS`
   - use `makeviewmigrations` command to create migrations for view models


### How to create view in your database?

- To create your view use DBView class, remember to set view definition attribute.


   ```python
    from django.db import models
    from django_db_views.db_view import DBView
    
    
    class VirtualCard(models.Model):
        ...
    
    
    class Balance(DBView):

        virtual_card = models.ForeignKey(
            VirtualCard,  # VirtualCard is a regular Django model. 
            on_delete=models.DO_NOTHING, related_name='virtual_cards'
        )
        total_discount = models.DecimalField(max_digits=12, decimal_places=2)
        total_returns = models.DecimalField(max_digits=12, decimal_places=2)
        balance = models.DecimalField(max_digits=12, decimal_places=2)
        
        view_definition = """
            SELECT
                row_number() over () as id,  # Django requires column called id
                virtual_card.id as virtual_card_id,
                sum(...) as total_discount,
            ...
        """
    
        class Meta:
            managed = False  # Managed must be set to False!
            db_table = 'virtual_card_balance'
   ```


- The view definition can be: **str/dict** or a callable which returns **str/dict**. 

   Callable view definition examples:

   ```python
    from django_db_views.db_view import DBViewl
  
    class ExampleView(DBView):
        @staticmethod
        def view_definition():
            #  Note for MySQL users:
            #    In the case of MySQL you might have to use: 
            #    connection.cursor().mogrify(*queryset.query.sql_with_params()).decode() instead of str method to get valid sql statement from Query.
            return str(SomeModel.objects.all().query)  

        # OR
        view_definition = lambda: str(SomeModel.objects.all().query)
        class Meta:
            managed = False 
            db_table = 'example_view'
   ```

   using callable allow you to write view definition using ORM.

- Ensure that you include `managed = False` in the DBView model's Meta class to prevent Django creating it's own migration.

### How view migrations work? 
   - DBView working as regular django model. You can use it in any query. 
   - It's using Django code, view-migrations looks like regular migrations. 
   - It relies on `db_table` names. 
   - `makeviewmigrations` command finds previous migration for view.
      - if there is no such migration then script create a new migration
      - if previous migration exists but no change in `view_definition` is detected nothing is done
      - if previous migration exists, then script will use previous `view_definition` for backward operation, and creates new migration.
      - when run it will check if the current default engine definined in django.settings is the same engine the view was defined with


### Multidatabase support
Yoy can define view_definition as
a dict for multiple engine types.

If you do not pass in an engine and have a str or callable the
engine will be defaulted to the default database defined in django.

It respects --database flag in the migrate command,
So you are able to define a specific view definitions for specific databases using the engine key.
If the key do not match your current database, view migration will be skipped.

Also, feature becomes useful if you use a different engine for local / dev / staging / production.

Example dict view definition:

```python
view_definition = {
    "django.db.backends.sqlite3": """
        SELECT
            row_number() over () as id,
            q.id as question_id,
            count(*) as total_choices
        FROM question q
        JOIN choice c on c.question_id = q.id
        GROUP BY q.id
    """,
    "django.db.backends.postgresql": """
        SELECT
            row_number() over () as id,
            q.id as question_id,
            count(*) as total_choices
        FROM question q
        JOIN choice c on c.question_id = q.id
        GROUP BY q.id
    """,
}
```

### CREATE OR REPLACE VIEW Support

By default, regular views use `CREATE OR REPLACE VIEW` for migrations (when supported by the database). This provides several benefits:

- **Atomic operation**: No moment where the view doesn't exist
- **Preserves dependencies**: Dependent views, functions, and triggers continue to work
- **Maintains permissions**: View ownership and permissions are preserved
- **Safer for production**: No risk of breaking dependent objects

#### Database Support

- **PostgreSQL & MySQL**: Use `CREATE OR REPLACE VIEW` by default
- **SQLite**: Automatically uses `DROP VIEW` + `CREATE VIEW` (SQLite doesn't support CREATE OR REPLACE)

The system automatically detects your database engine and uses the appropriate approach.

#### Controlling the Behavior

You can control whether a view uses CREATE OR REPLACE with the `use_replace_migration` attribute:

```python
from django_db_views.db_view import DBView

class MyView(DBView):
    use_replace_migration = False  # Force DROP+CREATE instead of CREATE OR REPLACE

    view_definition = """
        SELECT id, name FROM my_table
    """

    class Meta:
        managed = False
        db_table = 'my_view'
```

Setting `use_replace_migration = False` forces the traditional `DROP VIEW` + `CREATE VIEW` approach, even on databases that support CREATE OR REPLACE.

#### Multi-Database Views

For views with different definitions per database engine, the decision is made at runtime based on the actual database being used:

```python
class MyView(DBView):
    view_definition = {
        "django.db.backends.postgresql": "SELECT ...",  # Uses CREATE OR REPLACE
        "django.db.backends.sqlite3": "SELECT ...",     # Uses DROP+CREATE
        "django.db.backends.mysql": "SELECT ...",       # Uses CREATE OR REPLACE
    }

    class Meta:
        managed = False
        db_table = 'my_view'
```

**Note**: Materialized views always use `DROP MATERIALIZED VIEW` + `CREATE MATERIALIZED VIEW` because PostgreSQL does not support CREATE OR REPLACE for materialized views.

### Materialized Views

Just inherit from `DBMaterializedView` instead of regular `DBView`

Materialized View provide an extra class method to refresh view called `refresh`

### Materialized View Indexes

Indexes on materialized views are automatically detected and managed in migrations.

When you create indexes on a materialized view and run `makeviewmigrations`, the indexes will be automatically detected and included in the migration. When the view definition changes and needs to be recreated, the indexes are automatically dropped before the view recreation and recreated afterwards.

Example workflow:
```python
# 1. Create your materialized view
class MyMaterializedView(DBMaterializedView):
    value = models.IntegerField()
    name = models.TextField()

    view_definition = """
        SELECT id, value, name FROM my_table
    """

    class Meta:
        managed = False
        db_table = 'my_materialized_view'

# 2. Run migrations to create the view
# python manage.py makeviewmigrations
# python manage.py migrate

# 3. Create indexes on the materialized view
# CREATE INDEX my_view_name_idx ON my_materialized_view (name);
# CREATE UNIQUE INDEX my_view_value_idx ON my_materialized_view (value) WHERE value > 0;

# 4. Run makeviewmigrations again - indexes are automatically detected
# python manage.py makeviewmigrations

# 5. The migration will include the index definitions
# When you later change view_definition, indexes will be automatically recreated
```

Supported index types:
- Regular indexes: `CREATE INDEX name ON table (column)`
- Unique indexes: `CREATE UNIQUE INDEX name ON table (column)`
- Multi-column indexes: `CREATE INDEX name ON table (col1, col2)`
- Partial indexes: `CREATE INDEX name ON table (column) WHERE condition`
- Different index methods: btree (default), hash, gin, gist, brin

Customizing index detection:

You can override `get_migration_indexes()` to customize which indexes are managed:

```python
class MyMaterializedView(DBMaterializedView):
    @classmethod
    def get_migration_indexes(cls, using=None):
        indexes = super().get_migration_indexes(using)
        # Remove an index that shouldn't be managed
        indexes.pop("system_generated_idx", None)
        # Or add a custom index definition
        indexes["custom_idx"] = {
            "columns": "custom_column",
            "unique": True,
            "method": "btree",
            "where_clause": None
        }
        return indexes
```

**Note:** Index management is currently only supported for PostgreSQL databases and assumes the 'public' schema. Support for other databases and custom schemas may be added in future versions.

### Notes
_Please use the newest version. version 0.1.0 has backward
incompatibility which is solved in version 0.1.1 and higher._
