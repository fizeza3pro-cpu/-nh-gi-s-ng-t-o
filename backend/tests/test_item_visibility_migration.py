"""Kiểm tra migration ẩn/hiện trên dữ liệu giả trong bộ nhớ."""

from pathlib import Path
import runpy

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_visibility_migration_preserves_existing_items():
    migration = runpy.run_path(str(Path(__file__).resolve().parents[1] / "alembic" / "versions"
                                  / "c4a6b8d0e125_add_survey_item_visibility.py"))
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT, description TEXT)")
        connection.exec_driver_sql("INSERT INTO items VALUES ('dua', 'Đũa', 'Mô tả cũ')")
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
            row = connection.exec_driver_sql("SELECT * FROM items").mappings().one()
            assert dict(row) == {"id": "dua", "name": "Đũa", "description": "Mô tả cũ", "survey_visible": 1}
            migration["downgrade"]()
        assert {column["name"] for column in inspect(connection).get_columns("items")} == {"id", "name", "description"}
        assert connection.exec_driver_sql("SELECT * FROM items").one() == ("dua", "Đũa", "Mô tả cũ")
    engine.dispose()
