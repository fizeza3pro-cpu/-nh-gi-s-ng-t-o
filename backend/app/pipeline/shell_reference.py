"""Bộ mã tham chiếu do AI biên soạn cho vỏ đạn; không phải mẫu chuẩn hóa tâm lý."""

from app.schemas.schemas import FunctionalSignature


def _entry(key, name, goal, role, mechanism, include, exclude, examples, aliases=()):
    return {
        "key": key, "name": name,
        "description": f"Dùng vỏ đạn để {goal}. {include}",
        "functional_signature": FunctionalSignature(goal=goal, object_role=role, mechanism=mechanism).model_dump(),
        "inclusion_rules": [include], "exclusion_rules": [exclude],
        "illustrative_examples": examples, "existing_names": list(aliases),
    }


# Ví dụ là câu minh họa tự soạn; không nhập vào ResponseIdea hoặc positive_examples.
SHELL_REFERENCE = [
    _entry("container", "Vỏ đạn làm vật chứa đựng", "chứa và giữ vật chất bên trong", "vật chứa rỗng", "khoang rỗng và thành vỏ giữ vật chất",
           "Nhận chứa đồ nhỏ, nước, bút, hoa hoặc đất trồng khi chức năng chính là chứa.",
           "Loại vỏ bảo vệ bộ máy, vật dùng làm khuôn và các ý chỉ trang trí không có chức năng chứa.",
           ["Làm lọ cắm hoa", "Đựng bút", "Đựng hạt giống"], ("Dùng vỏ đạn làm vật chứa đựng",)),
    _entry("jewelry", "Vỏ đạn làm trang sức", "trang sức đeo trên cơ thể", "thành phần trang sức", "hình dáng và bề mặt kim loại tạo chi tiết đeo",
           "Nhận mặt dây chuyền, vòng, khuyên tai có mục đích trang sức.",
           "Loại chi tiết gắn lên đồ vật, mô hình trưng bày; tặng người khác chỉ là bối cảnh nếu đã nêu sản phẩm trang sức.",
           ["Làm mặt dây chuyền", "Làm khuyên tai"], ("Gia công vỏ đạn thành trang sức đeo trên người",)),
    _entry("model", "Vỏ đạn làm mô hình trưng bày", "tạo mô hình để trưng bày", "vật liệu tạo hình", "ghép hình khối của vỏ thành mô hình",
           "Nhận mô hình, tượng có mục đích trưng bày được nêu rõ.",
           "Loại đồ chơi để chơi, mô hình dạy học và sản phẩm có chức năng sử dụng khác được nêu rõ.",
           ["Ghép thành mô hình xe để trưng bày", "Làm tượng trang trí"], ("Lắp ráp mô hình trang trí từ vỏ đạn",)),
    _entry("ornament", "Vỏ đạn làm chi tiết trang trí", "trang trí bề mặt đồ vật", "chi tiết trang trí", "hình dáng và bề mặt vỏ tạo điểm nhấn thị giác",
           "Nhận chi tiết gắn lên khung ảnh, quần áo hoặc đồ dùng nhằm làm đẹp.",
           "Loại trang sức độc lập, mô hình trưng bày và dấu hiệu dùng để truyền thông tin.",
           ["Trang trí khung ảnh", "Đính lên áo làm họa tiết"], ("Dùng vỏ đạn làm phụ kiện trang trí đính lên đồ vật",)),
    _entry("gift", "Vỏ đạn làm quà kỷ niệm", "trao tặng kỷ vật", "vật trao tặng mang ý nghĩa", "trao vật để biểu đạt tình cảm hoặc kỷ niệm",
           "Nhận tặng vỏ đạn làm quà khi chưa nêu một công dụng sản phẩm cụ thể khác.",
           "Loại bán lấy tiền; nếu làm vòng cổ để tặng thì nhận công dụng trang sức, không đếm tặng thành ý thứ hai.",
           ["Tặng bạn làm kỷ niệm", "Làm kỷ vật tặng đồng đội"], ("Tặng vỏ đạn làm quà lưu niệm",)),
    _entry("recycle", "Vỏ đạn làm nguồn kim loại tái chế", "thu hồi nguyên liệu kim loại", "nguồn vật liệu", "thu hồi kim loại của vỏ làm nguyên liệu",
           "Nhận tái chế thu kim loại khi chưa nêu một sản phẩm có chức năng cuối cụ thể.",
           "Loại bán nguyên vỏ lấy tiền; khi đã nêu sản phẩm cuối thì ưu tiên chức năng của sản phẩm đó.",
           ["Tái chế lấy kim loại làm nguyên liệu"], ("Thu hồi giá trị kim loại từ vỏ đạn",)),
    _entry("housing", "Vỏ đạn làm vỏ bảo vệ thiết bị", "bao bọc bộ phận thiết bị", "vỏ thiết bị", "thành vỏ bao quanh và giữ bộ phận bên trong",
           "Nhận vỏ cho bộ máy hoặc linh kiện khi vai trò của vỏ đạn là bao bọc thiết bị.",
           "Loại chứa vật rời, trang sức không có bộ máy, hoặc dùng vỏ như dây dẫn điện.",
           ["Làm vỏ cho một thiết bị nhỏ"], ("Gia công vỏ đạn làm vỏ chứa bộ máy thiết bị nhỏ",)),
    _entry("dig", "Vỏ đạn làm dụng cụ đào xới", "đào xới đất", "dụng cụ tác động lên đất", "thành hoặc miệng vỏ tác động cơ học lên đất",
           "Nhận đào, xới, cào đất bằng vỏ đạn.",
           "Loại dùng vỏ chứa đất hoặc làm vật đánh dấu luống cây.",
           ["Xới đất trong chậu", "Dùng để đào đất"], ("Dùng vỏ đạn làm dụng cụ đào/xới đất",)),
    _entry("weight", "Vỏ đạn làm vật chặn và đối trọng", "giữ ổn định bằng trọng lượng", "vật nặng hoặc đối trọng", "trọng lượng vỏ giữ vật hoặc cân bằng lực",
           "Nhận chặn giấy, chặn cửa, đối trọng, vật dằn khi khai thác khối lượng.",
           "Loại ném gây tác động, kê đỡ nhờ hình dạng và dùng vật làm đơn vị đếm.",
           ["Chặn giấy khỏi bay", "Làm đối trọng cho mô hình"]),
    _entry("sound", "Vỏ đạn làm vật phát âm thanh", "phát âm thanh hoặc tạo nhịp", "vật rung phát âm", "va chạm hoặc rung của vỏ tạo tiếng",
           "Nhận chuông gió, nhạc cụ gõ, tiếng báo hiệu khi âm thanh là chức năng chính.",
           "Loại đồ trang trí không nêu phát âm và dấu hiệu thị giác không có âm thanh.",
           ["Làm chuông gió", "Gõ tạo nhịp cho bài hát"]),
    _entry("play", "Vỏ đạn làm quân và đạo cụ trò chơi", "phục vụ hoạt động chơi", "quân chơi hoặc đạo cụ", "dùng hình dạng và khả năng thao tác của vỏ trong trò chơi",
           "Nhận quân cờ, đồ chơi và vật chơi có hoạt động chơi được nêu rõ.",
           "Loại mô hình chỉ trưng bày, công cụ học đếm, hành vi ném nhau không nêu trò chơi.",
           ["Làm quân cờ", "Làm đồ chơi xếp hình"]),
    _entry("count", "Vỏ đạn làm vật đếm và chia nhóm", "biểu diễn số lượng hoặc chia nhóm", "đơn vị đếm", "mỗi vỏ đại diện một đơn vị hoặc một nhóm",
           "Nhận học đếm, tính điểm, chia nhóm bằng số lượng vỏ.",
           "Loại quân cờ dùng trong trò chơi, nhãn định danh cá thể và vật nặng để cân bằng.",
           ["Dùng để học đếm", "Mỗi vỏ đại diện một điểm chuyên cần"]),
    _entry("sale", "Vỏ đạn làm vật trao đổi lấy giá trị", "thu tiền hoặc trao đổi hàng hóa", "vật có giá trị trao đổi", "chuyển quyền sở hữu vỏ để nhận giá trị",
           "Nhận bán nguyên vỏ hoặc trao đổi khi lợi ích kinh tế là mục đích được nêu.",
           "Loại thu hồi nguyên liệu qua tái chế, trao tặng miễn phí và chế tạo sản phẩm với công dụng cụ thể.",
           ["Bán phế liệu lấy tiền", "Đổi lấy món đồ khác"]),
    _entry("teaching", "Vỏ đạn làm mẫu vật học tập", "minh họa kiến thức bằng mẫu vật", "mẫu quan sát", "quan sát hình dạng và đặc điểm của vỏ để học hoặc giải thích",
           "Nhận mẫu dạy học vật liệu, lịch sử hoặc cấu tạo ở mức quan sát.",
           "Loại dùng vỏ chỉ để đếm, trưng bày thuần trang trí và lưu vật chứng cho điều tra.",
           ["Làm mẫu vật cho bài học về kim loại", "Minh họa hiện vật lịch sử"]),
    _entry("evidence", "Vỏ đạn làm vật chứng và tư liệu", "lưu giữ bằng chứng hoặc tư liệu sự kiện", "hiện vật mang dấu vết", "giữ và đối chiếu dấu vết sẵn có trên vỏ",
           "Nhận lưu hiện vật làm bằng chứng hoặc tư liệu nghiên cứu về một sự kiện cụ thể.",
           "Loại mẫu minh họa dạy học chung, quà kỷ niệm và thêm ký hiệu để đánh dấu vị trí.",
           ["Giữ làm vật chứng", "Lưu làm tư liệu hiện vật của sự kiện"]),
    _entry("marker", "Vỏ đạn làm dấu hiệu định danh", "đánh dấu vị trí hoặc nhận diện", "vật mang dấu hiệu", "đặt hoặc gắn vỏ để phân biệt vị trí và đối tượng",
           "Nhận đánh dấu luống, vị trí, đồ dùng hoặc nhãn nhận diện bằng vỏ.",
           "Loại trang trí chỉ làm đẹp, đếm số lượng và báo hiệu bằng âm thanh.",
           ["Đánh dấu vị trí gieo hạt", "Làm dấu nhận diện đồ dùng"]),
    _entry("support", "Vỏ đạn làm vật kê đỡ", "nâng đỡ hoặc giữ vị trí bằng hình dạng", "chi tiết kê đỡ", "thân vỏ tạo điểm tựa hoặc giữ vật đúng vị trí",
           "Nhận chân kê, giá đỡ, vật chèn bằng hình dạng khi nêu chức năng đỡ giữ.",
           "Loại đối trọng dựa vào khối lượng, chứa vật trong khoang và bộ phận lăn để di chuyển.",
           ["Kê đồ vật cho khỏi nghiêng", "Làm chân đỡ mô hình"]),
    _entry("electric", "Vỏ đạn làm phần tử dẫn điện", "dẫn điện trong mạch", "phần tử dẫn điện", "kim loại của vỏ tạo đường dẫn điện",
           "Nhận tiếp điểm hoặc đoạn nối khi vỏ được dùng vì khả năng dẫn điện.",
           "Loại vỏ thiết bị chỉ bảo vệ linh kiện; không suy ra dẫn điện từ câu chung chung làm thiết bị.",
           ["Làm tiếp điểm dẫn điện trong mô hình học tập"]),
    _entry("thermal", "Vỏ đạn làm phần tử truyền nhiệt", "truyền hoặc phân tán nhiệt", "phần tử truyền nhiệt", "kim loại của vỏ trao đổi nhiệt với vật tiếp xúc",
           "Nhận truyền nhiệt, tản nhiệt khi mục đích nhiệt được nêu rõ.",
           "Loại làm nhiên liệu, làm thức ăn, chứa thức ăn hoặc vỏ thiết bị không nêu chức năng nhiệt.",
           ["Làm chi tiết tản nhiệt cho mô hình"]),
    _entry("symbol", "Vỏ đạn làm biểu tượng truyền thông điệp", "truyền thông điệp qua ý nghĩa biểu tượng", "vật biểu tượng", "ý nghĩa gắn với vỏ đạn gợi thông điệp cho người xem",
           "Nhận biểu tượng hòa bình, thông điệp phản chiến hoặc đe dọa được nêu rõ ở mức ý nghĩa.",
           "Loại ném gây tác động vật lý, quà tặng chỉ mang tình cảm, trang trí thuần hình thức và mẫu dạy học.",
           ["Dùng trong tác phẩm truyền thông điệp hòa bình", "Dùng làm biểu tượng cảnh báo"]),
]


def plan_shell_reference(existing):
    """Tái dùng mã đúng tên đã đối chiếu; không tự gộp hay sửa phạm vi mã hiện có."""
    from app.pipeline.dynamic_mapping import normalize_code_name
    by_name = {row.normalized_name: row for row in existing}
    plan = []
    for entry in SHELL_REFERENCE:
        matches = [by_name[name] for name in {
            normalize_code_name(value) for value in [entry["name"], *entry["existing_names"]]
        } if name in by_name]
        if len(matches) > 1:
            raise ValueError(f"Nhiều mã cùng khớp tham chiếu {entry['key']}; cần đối chiếu trước khi nạp.")
        match = matches[0] if matches else None
        if match and (match.validation_status.value != "ACCEPTED" or match.maturity_status.value != "ACTIVE"):
            raise ValueError(f"Mã {entry['key']} đã bị loại/gộp; không tự kích hoạt lại.")
        plan.append((entry, match))
    return plan
