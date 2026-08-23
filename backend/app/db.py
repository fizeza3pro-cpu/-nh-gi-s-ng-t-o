

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tạo toàn bộ bảng theo model hiện có. Dùng cho dev/lần đầu setup.

    Ở giai đoạn sau khi đã ổn định schema, nên chuyển sang dùng Alembic
    (`alembic upgrade head`) thay vì gọi hàm này, để có lịch sử migration.
    """
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)