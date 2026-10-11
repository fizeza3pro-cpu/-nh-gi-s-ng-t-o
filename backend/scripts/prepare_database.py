"""Chuẩn bị DB triển khai: DB trống dùng schema hiện tại; DB có version dùng Alembic."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.db import Base, engine
from app.models import models  # noqa: F401 - đăng ký đủ metadata


# Danh mục sau migration a8c0e2f4b569, chỉ dùng khi DB mới hoàn toàn.
INITIAL_ITEMS = (
    ("balo_quan_nhu", "Balo quân nhu", "Trang bị cá nhân dùng hằng ngày, có nhiều khoang và dây đeo."),
    ("bi_dong_nuoc", "Bi đông nước", "Bình đựng nước cá nhân dạng trụ, thường làm bằng kim loại hoặc nhựa cứng."),
    ("xeng_cong_binh", "Xẻng công binh", "Dụng cụ đào nhỏ gọn dùng trong hoạt động công binh và dã ngoại."),
    ("mu_coi", "Mũ cối", "Mũ bảo hộ có dạng vòm, quen thuộc trong môi trường quân đội."),
    ("vo_dan", "Vỏ đạn", "Phần vỏ kim loại rỗng còn lại sau khi viên đạn đã được sử dụng."),
    ("thung_dan", "Thùng đạn", "Thùng hình hộp chắc chắn dùng để chứa và vận chuyển đạn dược."),
    ("ni_long_ao_mua", "Ni lông (áo mưa)", "Tấm vật liệu ni lông mềm, chống nước, thường được dùng làm áo mưa."),
    ("kinh_lup", "Kính lúp", "Thấu kính cầm tay dùng để quan sát vật thể ở kích thước phóng đại."),
    ("ong_nghiem", "Ống nghiệm", "Ống nhỏ hình trụ dùng trong phòng thí nghiệm để chứa mẫu hoặc chất lỏng."),
    ("can_tieu_ly", "Cân tiểu ly", "Dụng cụ cân nhỏ dùng để đo khối lượng với độ chính xác cao."),
    ("ghim_kep_giay", "Ghim kẹp giấy", "Kẹp kim loại nhỏ dùng để giữ các tờ giấy cùng nhau."),
    ("cuon_chi", "Cuộn chỉ", "Sợi chỉ dài được quấn quanh một lõi nhỏ thành cuộn."),
)


def prepare_database(target_engine=engine) -> None:
    """Không stamp DB có dữ liệu chưa version; mọi DDL nằm trong một transaction."""
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with target_engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        config.attributes["connection"] = connection
        if not tables:
            # Migration lịch sử đầu tiên giả định schema legacy đã tồn tại.
            # Chỉ DB thực sự trống được khởi tạo thẳng theo metadata hiện hành.
            Base.metadata.create_all(connection)
            connection.execute(models.Item.__table__.insert(), [
                {"id": key, "name": name, "description": description}
                for key, name, description in INITIAL_ITEMS
            ])
            command.stamp(config, "head")
        elif "alembic_version" not in tables:
            raise RuntimeError("DB có bảng nhưng chưa có Alembic version. Cần kiểm tra schema và version trước khi triển khai; không tự stamp.")
        else:
            command.upgrade(config, "head")


if __name__ == "__main__":
    prepare_database()
