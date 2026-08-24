"""
    uv run python -m code_test
"""

from app.core.security import hash_password
from app.db import SessionLocal, init_db
from app.models.models import User as UserModel

SEED_USERS = [
    {"username": "admin", "password": "admin12345", "full_name": "Quản trị viên", "role": "admin"},
    {"username": "user1", "password": "user12345", "full_name": "Người dùng 1", "role": "user"},
    {"username": "user2", "password": "user12345", "full_name": "Người dùng 2", "role": "user"},
]


def main() -> None:
    init_db()  # đảm bảo bảng đã tồn tại
    db = SessionLocal()
    try:
        created = 0
        for u in SEED_USERS:
            existing = db.query(UserModel).filter(UserModel.username == u["username"]).first()
            if existing:
                print(f"[bỏ qua] username='{u['username']}' đã tồn tại.")
                continue

            db.add(
                UserModel(
                    username=u["username"],
                    password_hash=hash_password(u["password"]),
                    full_name=u["full_name"],
                    role=u["role"],
                )
            )
            created += 1
            print(f"[tạo mới] username='{u['username']}' role='{u['role']}'")

        db.commit()
        print(f"\nHoàn tất — đã tạo {created} user mới.")
    finally:
        db.close()


if __name__ == "__main__":
    main()