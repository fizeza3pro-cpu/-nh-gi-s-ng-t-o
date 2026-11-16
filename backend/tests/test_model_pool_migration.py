"""Diễn tập migration trên dữ liệu giả, kiểm tra không sửa bảng khảo sát."""
from pathlib import Path
import runpy
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_pool_migration_is_additive_and_preserves_survey_tables():
    migration = runpy.run_path(str(Path(__file__).resolve().parents[1] / "alembic/versions/c5b7d9e1f236_add_byteplus_model_pool.py"))
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE responses (id TEXT PRIMARY KEY, scoring TEXT)")
        connection.exec_driver_sql("INSERT INTO responses VALUES ('final', '{\"frozen\": true}')")
        before = connection.exec_driver_sql("SELECT * FROM responses").all()
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
            assert connection.exec_driver_sql("SELECT enabled, threshold FROM model_pool_settings").one() == (0, 10000)
            assert connection.exec_driver_sql("SELECT * FROM responses").all() == before
            migration["downgrade"]()
        assert inspect(connection).get_table_names() == ["responses"]
        assert connection.exec_driver_sql("SELECT * FROM responses").all() == before
    engine.dispose()
