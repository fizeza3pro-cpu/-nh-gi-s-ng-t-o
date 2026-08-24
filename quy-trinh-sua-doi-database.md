# Quy trình thay đổi cấu trúc Database (SQLAlchemy + Alembic + uv)

Ghi lại các bước cần làm mỗi khi sửa model (thêm cột, đổi tên cột, xóa cột...) trong file định nghĩa model (`db.py` / `models.py`) và muốn áp dụng thay đổi đó vào PostgreSQL thật.

---

## 0. Nguyên tắc cần nhớ

> Sửa code Python (class `User(Base)`...) **không tự động** cập nhật database.
> Model Python chỉ là "bản thiết kế mong muốn". Phải dùng Alembic để so sánh bản thiết kế đó với database thật, rồi tạo lệnh thay đổi (migration) và áp dụng nó.

---

## 1. Cấu hình một lần duy nhất (đã làm xong, chỉ cần biết để hiểu vì sao mọi thứ hoạt động)

- `alembic.ini`: có `script_location = %(here)s/alembic`. Dòng `sqlalchemy.url = driver://...` là giá trị mẫu, **không dùng tới** vì đã override trong `env.py`.
- `alembic/env.py`: đã sửa để:
  - Import `settings` từ `app/config.py` → lấy đúng `DATABASE_URL` trong `.env`
  - Import `Base` và `models` từ `app/db.py` → để Alembic biết hết các bảng/cột hiện có trong model
  - Dòng `config.set_main_option("sqlalchemy.url", settings.database_url)` để dùng URL thật thay vì URL mẫu

---

## 2. Quy trình chuẩn mỗi khi sửa model

### Bước 1 — Sửa model trong code

Ví dụ trong `app/models.py` hoặc `app/db.py`, sửa/thêm/xóa field trong class (`User`, `Item`...).

### Bước 2 — Tạo file migration tự động

```powershell
uv run alembic revision --autogenerate -m "mô tả ngắn gọn thay đổi"
```

Ví dụ: `-m "rename column email to username"`, `-m "add phone number to user"`.

Lệnh này **chỉ tạo file**, chưa đụng vào database thật. File sinh ra nằm ở:
```
alembic/versions/<mã_revision>_<mô_tả>.py
```

### Bước 3 — ⚠️ BẮT BUỘC: Mở file migration vừa tạo lên kiểm tra

```powershell
code alembic\versions\<tên_file>.py
```

Trong file sẽ có 2 hàm `upgrade()` (áp dụng thay đổi) và `downgrade()` (hoàn tác thay đổi).

**Kiểm tra xem Alembic có hiểu đúng ý định không:**

| Trường hợp | Alembic tự sinh ra gì | Có đúng ý không? |
|---|---|---|
| Thêm cột mới hoàn toàn | `op.add_column(...)` | ✅ Đúng, giữ nguyên |
| Xóa hẳn 1 cột không dùng nữa | `op.drop_column(...)` | ✅ Đúng, nhưng nhớ là mất data cột đó |
| **Đổi tên cột** (ví dụ `email` → `username`) | Bị hiểu nhầm thành: `op.add_column(cột mới)` + `op.drop_column(cột cũ)` | ❌ **SAI** — sẽ mất toàn bộ dữ liệu cũ! Phải sửa tay |

### Bước 4 — Nếu là đổi tên cột: sửa lại thành `alter_column`

**Sai (bản auto-generate, gây mất dữ liệu):**
```python
def upgrade() -> None:
    op.add_column('users', sa.Column('username', sa.String(length=255), nullable=False))
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.drop_column('users', 'email')
```

**Sửa lại thành (giữ nguyên dữ liệu):**
```python
def upgrade() -> None:
    op.alter_column('users', 'email', new_column_name='username')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
```

Làm tương tự (theo chiều ngược lại) cho `downgrade()`:
```python
def downgrade() -> None:
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.alter_column('users', 'username', new_column_name='email')
```

> Lưu ý: phần đổi tên **index** (`drop_index` + `create_index`) vẫn giữ nguyên như bản auto-generate — đây không phải xóa dữ liệu, chỉ đổi tên định danh index cho khớp tên cột mới, hoàn toàn an toàn.

### Bước 5 — Áp dụng migration vào database thật

```powershell
uv run alembic upgrade head
```

Đến bước này PostgreSQL mới **thực sự thay đổi**.

### Bước 6 — Kiểm tra lại trong PostgreSQL

```sql
\d users
```
hoặc
```sql
SELECT id, username FROM users LIMIT 5;
```

---

## 3. Các lệnh Alembic hữu ích khác

| Lệnh | Công dụng |
|---|---|
| `uv run alembic current` | Xem DB đang ở version migration nào |
| `uv run alembic history` | Xem toàn bộ lịch sử migration |
| `uv run alembic downgrade -1` | Lùi lại 1 migration gần nhất (hoàn tác) |
| `uv run alembic upgrade head` | Áp dụng tất cả migration chưa chạy, đưa DB lên bản mới nhất |

---

## 4. Ghi nhớ về `uv`

- Luôn dùng `uv add <package>` để cài package mới — **không dùng `pip install`** trực tiếp, vì `pip install` không ghi vào `pyproject.toml`/`uv.lock`, lần sau `uv sync` sẽ tự gỡ package đó đi (tưởng nhầm là "không thuộc project").
- `uv sync`: đồng bộ `.venv` khớp đúng với `uv.lock` — không cần activate `.venv` trước khi chạy.
- `uv run <lệnh>`: chạy lệnh bằng đúng Python/packages trong `.venv` của project, không cần activate thủ công.

---

## 5. Checklist nhanh mỗi lần đổi schema

- [ ] Sửa model trong code
- [ ] `uv run alembic revision --autogenerate -m "..."`
- [ ] Mở file migration vừa tạo, đọc kỹ `upgrade()`/`downgrade()`
- [ ] Nếu là rename cột → sửa `add_column`+`drop_column` thành `alter_column`
- [ ] `uv run alembic upgrade head`
- [ ] Kiểm tra lại trong PostgreSQL (`\d <table>` hoặc query thử)
