"""Mã và phân bố GIẢ ĐỊNH cho ba đồ vật PILOT; không phải tần suất dân số."""

from app.schemas.schemas import FunctionalSignature


# Mỗi mã tối đa một lần trong mỗi lượt; mã ít dễ liên tưởng chỉ có 1–2 ý.
RANK_COUNTS = (15, 15, 15, 15, 15, 12, 12, 10, 8, 7, 6, 5, 4, 3, 2, 2, 1, 1, 1, 1)


def entry(key, name, goal, role, mechanism, example, exclude, aliases=()):
    """Tách ví dụ minh họa khỏi ví dụ quan sát và mô tả ranh giới chức năng."""
    return {
        "key": key, "name": name, "description": f"{goal}; {mechanism}.",
        "functional_signature": FunctionalSignature(goal=goal, object_role=role, mechanism=mechanism).model_dump(),
        "inclusion_rules": [f"Nhận công dụng có mục đích {goal}, vật đóng vai trò {role}."],
        "exclusion_rules": [exclude], "illustrative_examples": [example], "existing_names": list(aliases),
    }


REFERENCES = {
    "cuon_chi": [
        entry("sewing", "Sợi chỉ dùng để khâu nối", "nối hoặc vá vải", "sợi khâu", "sợi luồn qua vải giữ các mép lại", "Dùng chỉ khâu vá áo rách", "Loại đan dệt từ sợi và khâu mô cơ thể."),
        entry("tie", "Sợi chỉ làm dây buộc cố định", "buộc giữ các vật với nhau", "dây buộc", "sợi quấn và thắt nút giữ vật", "Buộc một bó que nhỏ", "Loại dây treo chịu tải, khâu vải và bện dây chưa nêu công dụng cuối."),
        entry("weave", "Sợi nguyên liệu để đan/dệt", "tạo tấm hoặc sản phẩm dệt", "sợi đan dệt", "các sợi đan xen thành cấu trúc liên kết", "Đan chỉ thành tấm lót cốc", "Loại khâu nối vải sẵn có, trang sức đeo và chỉ bện thành dây."),
        entry("ornament", "Vật treo trang trí", "trang trí không gian", "vật treo trang trí", "hình dáng và màu sắc cuộn chỉ tạo điểm nhấn", "Treo cuộn chỉ lên cây thông trang trí", "Loại dây treo để giữ đồ dùng và đồ trang sức đeo trên người."),
        entry("jewelry", "Sợi chỉ làm trang sức", "trang sức đeo trên người", "vật liệu trang sức", "kết sợi thành vật đeo", "Kết chỉ thành vòng tay", "Loại bện dây nguyên liệu và đồ trang trí không đeo."),
        entry("hang", "Sợi chỉ làm dây treo đồ nhẹ", "treo giữ vật nhẹ", "dây treo chịu lực", "lực căng sợi giữ vật bên dưới điểm treo", "Làm dây treo ảnh lên tường", "Loại cuộn chỉ tự làm đồ trang trí và buộc bó vật nằm trên mặt bàn."),
        entry("measure", "Sợi chỉ làm dụng cụ đo chiều dài", "đo chiều dài hoặc chu vi", "dây đo", "áp sợi theo đường cần đo rồi đối chiếu chiều dài", "Đo chu vi chai bằng sợi chỉ rồi đối chiếu thước", "Loại dây dọi xác định phương thẳng đứng và dây chỉ để đánh dấu."),
        entry("marker", "Sợi chỉ làm dấu nhận diện", "đánh dấu vị trí hoặc nhận diện", "dấu chỉ", "màu hoặc vị trí sợi phân biệt điểm cần nhớ", "Kẹp sợi chỉ vào sách để đánh dấu trang", "Loại đo chiều dài, trang trí và căng dây để vẽ hình."),
        entry("pet_play", "Đồ chơi giải trí cho vật nuôi", "cho vật nuôi chơi", "đồ chơi di chuyển", "cuộn chỉ lăn tạo vật để đuổi theo", "Lăn cuộn chỉ làm đồ chơi cho mèo", "Loại chơi thể thao của người và trang trí hình con vật."),
        entry("braid", "Bện chỉ thành sợi dây", "tạo dây nguyên liệu", "sợi để bện", "nhiều sợi xoắn hoặc bện tạo dây", "Bện nhiều sợi chỉ thành dây", "Nếu đã nêu chức năng cuối như vòng tay hoặc dây treo thì ưu tiên chức năng cuối."),
        entry("gift", "Vật phẩm làm quà tặng", "trao tặng kỷ vật", "vật trao tặng", "trao vật để biểu đạt tình cảm", "Tặng cuộn chỉ làm quà kỷ niệm", "Loại tự giữ kỷ niệm và sản phẩm có công dụng cuối rõ như vòng tay để tặng."),
        entry("memory", "Vật lưu niệm giữ kỷ niệm", "lưu giữ kỷ niệm", "kỷ vật cá nhân", "giữ vật gắn với ký ức", "Giữ cuộn chỉ làm kỷ niệm nghề may của bà", "Loại trao tặng cho người khác hoặc trưng bày chỉ để làm đẹp."),
        entry("sports", "Vật tròn thay thế để chơi thể thao", "chơi thể thao dùng vật tròn", "bóng thay thế", "cuộn chỉ tròn có thể lăn hoặc được chuyền", "Dùng cuộn chỉ làm bóng chuyền tay trong trò chơi", "Loại đồ chơi riêng cho vật nuôi và con lăn vận chuyển đồ."),
        entry("teaching", "Cuộn chỉ làm mẫu học tập", "minh họa kiến thức vật liệu", "mẫu quan sát", "quan sát cấu trúc sợi để học", "Làm mẫu quan sát cấu trúc sợi trong bài học dệt may", "Loại dụng cụ đo, đánh dấu hoặc trò chơi không có mục tiêu học tập."),
        entry("wick", "Sợi chỉ làm bấc dẫn chất lỏng", "dẫn chất lỏng bằng mao dẫn", "bấc thấm hút", "khe giữa sợi dẫn chất lỏng", "Dùng chỉ bông làm bấc dẫn nước cho chậu cây nhỏ", "Loại dây treo chậu và cuộn chỉ làm bình chứa nước."),
        entry("plumb", "Sợi chỉ làm dây dọi", "xác định phương thẳng đứng", "dây treo quả dọi", "trọng lực kéo thẳng sợi có vật nặng", "Treo vật nặng bằng chỉ làm dây dọi kiểm tra độ thẳng", "Loại đo chiều dài bằng dây và treo đồ để cất giữ."),
        entry("vibration", "Sợi chỉ truyền dao động âm", "truyền dao động để nghe", "dây truyền rung", "sợi căng truyền dao động giữa hai đầu", "Căng chỉ nối hai cốc giấy làm điện thoại đồ chơi", "Loại dây treo hoặc đồ chơi không sử dụng truyền rung."),
        entry("draw", "Sợi chỉ dẫn hướng vẽ hình", "dẫn đường vẽ hình", "dây giới hạn quỹ đạo", "sợi căng giữ khoảng cách bút tới điểm cố định", "Buộc chỉ vào bút và điểm tâm để vẽ đường tròn", "Loại đo chiều dài đơn thuần hoặc để dấu nhận diện."),
        entry("slice", "Sợi chỉ làm dây cắt vật mềm", "chia cắt vật mềm", "dây cắt", "sợi căng tạo áp lực trên đường hẹp", "Căng chỉ để cắt đất nặn thành lát", "Loại buộc giữ vật và sợi khâu."),
        entry("roller", "Lõi cuộn chỉ làm con lăn", "giảm lực cản khi di chuyển đồ nhỏ", "con lăn", "lõi tròn lăn dưới vật", "Đặt lõi cuộn chỉ làm con lăn dưới hộp đồ chơi", "Loại bóng chơi và dây kéo không dùng chuyển động lăn."),
    ],
    "xeng_cong_binh": [
        entry("dig", "Xẻng dùng đào xới đất", "đào hoặc xới đất", "lưỡi đào", "lưỡi xuyên và tách đất", "Đào hố trồng cây bằng xẻng", "Loại chỉ xúc vật liệu rời có sẵn và đo độ sâu."),
        entry("scoop", "Xẻng xúc chuyển vật liệu rời", "chuyển vật liệu rời", "mặt xúc", "mặt lưỡi đỡ và mang vật liệu", "Xúc cát chuyển vào bao", "Loại đào đất nguyên khối và mái chèo tạo lực trong nước."),
        entry("hammer", "Xẻng làm dụng cụ đóng gõ", "đóng vật bằng va đập", "búa thay thế", "khối lượng xẻng truyền xung lực khi gõ", "Dùng mặt xẻng đóng cọc lều", "Loại gõ để phát âm và dùng trọng lượng chặn tĩnh."),
        entry("cut", "Cạnh xẻng cắt chia vật liệu", "cắt chia vật liệu", "lưỡi cắt", "cạnh lưỡi tác động tập trung làm tách vật", "Dùng cạnh xẻng cắt dây buộc bao", "Loại đào đất hoặc bẩy vật nguyên khối."),
        entry("lever", "Xẻng làm đòn bẩy", "bẩy nâng vật", "đòn bẩy", "cán và lưỡi truyền lực qua điểm tựa", "Luồn xẻng làm đòn bẩy nâng hòn đá", "Loại kê đỡ tĩnh hoặc mang vật đi nơi khác."),
        entry("paddle", "Xẻng làm mái chèo", "đẩy phương tiện trên nước", "mái chèo", "mặt lưỡi đẩy nước tạo lực phản hồi", "Dùng xẻng làm mái chèo cho bè nhỏ", "Loại xúc nước để chuyển sang vật chứa."),
        entry("fan", "Xẻng làm quạt tay", "tạo luồng gió", "mặt quạt", "chuyển động mặt lưỡi đẩy không khí", "Quạt gió bằng mặt xẻng", "Loại tấm chắn gió hoặc chắn bức xạ nhiệt."),
        entry("support", "Xẻng làm giá chống đỡ", "chống đỡ vật tại chỗ", "thanh chống", "cán cứng truyền lực xuống điểm tựa", "Dùng cán xẻng chống tấm bạt che", "Loại đòn bẩy nâng động, cáng vận chuyển và vật chặn bằng trọng lượng."),
        entry("weight", "Xẻng làm vật chặn bằng trọng lượng", "giữ vật bằng trọng lượng", "vật nặng", "khối lượng xẻng dằn vật xuống", "Đè xẻng lên mép bạt để khỏi bay", "Loại chống đỡ theo hình dạng và đóng vật bằng va đập."),
        entry("sound", "Xẻng làm dụng cụ phát âm", "phát âm thanh hoặc nhịp", "vật rung phát âm", "va chạm mặt kim loại tạo tiếng", "Gõ xẻng làm tiếng báo tập trung", "Loại đóng cọc và báo hiệu bằng ánh sáng."),
        entry("cook", "Mặt xẻng làm bề mặt truyền nhiệt nấu ăn", "làm nóng thức ăn", "bề mặt nấu", "mặt kim loại truyền nhiệt tới thức ăn", "Dùng mặt xẻng sạch làm bề mặt nướng thức ăn", "Loại chỉ xúc thức ăn hoặc che chắn nguồn nhiệt."),
        entry("marker", "Xẻng làm mốc vị trí", "đánh dấu một vị trí", "vật mốc", "đặt xẻng dễ nhìn để nhận ra vị trí", "Cắm xẻng làm mốc đầu luống", "Loại đo khoảng cách, trang trí hoặc phản chiếu ánh sáng báo hiệu."),
        entry("measure", "Xẻng làm thước đo tương đối", "ước lượng chiều dài hoặc độ sâu", "đơn vị đo", "so kích thước đã biết của xẻng với khoảng cần đo", "Dùng chiều dài cán xẻng ước lượng độ sâu hố", "Loại chỉ đánh dấu vị trí và đào hố."),
        entry("ornament", "Xẻng làm vật trang trí", "trang trí không gian", "vật trưng bày", "hình dạng xẻng tạo bố cục thị giác", "Sơn xẻng rồi treo làm đồ trang trí", "Loại mẫu học tập hoặc tặng nguyên vật làm kỷ niệm."),
        entry("gift", "Xẻng làm quà kỷ niệm", "trao tặng kỷ vật", "vật trao tặng", "trao vật gắn với ý nghĩa kỷ niệm", "Tặng xẻng làm quà kỷ niệm đợt công tác", "Loại bán lấy tiền và sản phẩm có chức năng cuối khác."),
        entry("teaching", "Xẻng làm mẫu học tập", "minh họa cấu tạo công cụ", "mẫu quan sát", "quan sát các bộ phận để học", "Dùng xẻng làm mẫu giới thiệu cấu tạo dụng cụ công binh", "Loại trưng bày thuần trang trí hoặc trực tiếp dùng làm đòn bẩy."),
        entry("signal", "Mặt xẻng phản chiếu ánh sáng báo hiệu", "báo vị trí bằng ánh sáng", "mặt phản chiếu", "mặt kim loại bóng phản xạ ánh sáng", "Dùng mặt xẻng kim loại bóng phản chiếu ánh sáng báo vị trí", "Loại gõ báo hiệu bằng tiếng và đặt làm mốc tĩnh."),
        entry("sale", "Xẻng làm vật trao đổi", "thu giá trị qua trao đổi", "hàng hóa", "chuyển quyền sở hữu để nhận giá trị", "Bán xẻng cũ lấy tiền", "Loại tặng miễn phí hoặc tái chế thành sản phẩm khác."),
        entry("heat_shield", "Xẻng làm tấm chắn bức xạ nhiệt", "chắn nhiệt chiếu trực tiếp", "tấm chắn", "mặt lưỡi cản đường bức xạ nhiệt", "Dựng mặt xẻng thành tấm chắn nhiệt cho đồ đặt cạnh bếp", "Loại truyền nhiệt để nấu và quạt tạo luồng khí."),
        entry("carry", "Cán xẻng làm khung mang tải", "mang tải đi nơi khác", "khung chịu tải", "cán cứng kết hợp vải phân bố tải khi khiêng", "Ghép hai cán xẻng với vải làm khung khiêng đồ", "Loại giá chống tĩnh hoặc xúc vật liệu bằng lưỡi."),
    ],
    "mu_coi": [
        entry("container", "Mũ cối làm vật chứa", "chứa vật bên trong", "vật chứa lõm", "lòng mũ giữ vật rời", "Lật mũ cối đựng hạt giống", "Loại xúc chuyển, tổ cư trú, khuôn tạo hình và đo lượng nước."),
        entry("scoop", "Mũ cối làm dụng cụ xúc", "xúc chuyển vật liệu", "gáo xúc", "lòng mũ hứng và chuyển vật liệu", "Dùng mũ cối xúc cát vào bao", "Loại chứa để cất giữ, quạt gió và sàng lọc."),
        entry("fan", "Mũ cối làm quạt tay", "tạo luồng gió", "mặt quạt", "vành và thân mũ đẩy không khí khi chuyển động", "Cầm mũ cối quạt mát", "Loại che nắng bằng cách đặt mũ cố định."),
        entry("protect", "Mũ cối bảo vệ đầu", "che bảo vệ đầu", "vật đội đầu", "vòm mũ che đầu và giảm tiếp xúc trực tiếp", "Đội mũ cối để che đầu khỏi cành cây thấp", "Loại đạo cụ diễn, bóng chơi và mái che cho cây."),
        entry("play", "Mũ cối làm đạo cụ trò chơi", "phục vụ trò chơi", "đích hoặc đạo cụ chơi", "hình dạng mũ tạo mục tiêu thao tác", "Đặt mũ cối làm đích ném bóng giấy", "Loại trang phục biểu diễn và công cụ minh họa học tập."),
        entry("costume", "Mũ cối làm phục trang biểu diễn", "thể hiện nhân vật", "đạo cụ hóa trang", "kiểu dáng mũ giúp nhận diện vai diễn", "Đội mũ cối diễn vai người lính trên sân khấu", "Loại đội để che bảo vệ và trang trí không có vai diễn."),
        entry("ornament", "Mũ cối làm vật trang trí", "trang trí không gian", "vật trưng bày", "màu sắc và hình dáng mũ tạo điểm nhấn", "Vẽ họa tiết lên mũ cối để treo trang trí", "Loại mẫu dạy học, lưu kỷ niệm cá nhân và hóa trang."),
        entry("support", "Mũ cối làm vật kê đỡ", "nâng đỡ đồ vật", "giá kê", "vòm mũ làm điểm tựa cho vật nhẹ", "Dùng mũ cối kê tấm biển giấy khi trưng bày", "Loại chứa trong lòng mũ hoặc làm khuôn ép tạo hình."),
        entry("marker", "Mũ cối làm mốc nhận diện", "đánh dấu vị trí", "vật mốc", "hình dáng dễ nhìn giúp nhận ra vị trí", "Đặt mũ cối làm mốc điểm tập kết đồ", "Loại đích trò chơi và đồ trang trí thuần hình thức."),
        entry("gift", "Mũ cối làm quà kỷ niệm", "trao tặng kỷ vật", "vật trao tặng", "trao vật để biểu đạt tình cảm", "Tặng mũ cối làm quà kỷ niệm", "Loại bán hoặc tự giữ kỷ niệm."),
        entry("sale", "Mũ cối làm vật trao đổi", "thu giá trị qua trao đổi", "hàng hóa", "chuyển quyền sở hữu để nhận giá trị", "Bán mũ cối cũ lấy tiền", "Loại tặng miễn phí và tái sử dụng trực tiếp."),
        entry("memory", "Mũ cối làm kỷ vật lưu giữ", "giữ ký ức cá nhân", "kỷ vật", "vật gắn với sự kiện gợi lại ký ức", "Giữ mũ cối làm kỷ niệm thời quân ngũ", "Loại trao tặng hoặc trưng bày chỉ để làm đẹp."),
        entry("teaching", "Mũ cối làm mẫu học tập", "minh họa kiến thức trang bị", "mẫu quan sát", "quan sát vật thật để học", "Dùng mũ cối làm mẫu giới thiệu trang bị qua các thời kỳ", "Loại phục trang sân khấu và trưng bày thuần trang trí."),
        entry("sieve", "Mũ cối làm dụng cụ sàng", "tách vật theo kích thước", "sàng có lỗ", "lỗ tạo thêm cho hạt nhỏ lọt qua", "Đục lỗ mũ cũ làm sàng tách cát khỏi sỏi", "Loại chứa vật hoặc xúc chuyển không có phân tách."),
        entry("nest", "Mũ cối làm tổ cư trú", "tạo chỗ trú hoặc làm tổ", "kết cấu tổ", "lòng mũ kết hợp vật lót tạo chỗ cư trú", "Lót rơm trong mũ cũ làm tổ cho chim", "Loại chỉ bỏ con vật vào mũ mà không nêu chỗ trú hoặc làm tổ."),
        entry("shade", "Mũ cối làm mái che cho vật nhỏ", "che nắng cho vật bên dưới", "mái che", "vòm mũ cản ánh nắng chiếu trực tiếp", "Kê mũ lên giá làm mái che nắng cho cây con", "Loại đội bảo vệ đầu, quạt và chứa đất trồng cây."),
        entry("rain_measure", "Mũ cối làm dụng cụ đo mưa", "ước lượng lượng mưa", "bộ hứng đo", "lòng mũ có lớp lót kín và vạch đo thu lượng nước", "Lót kín mũ và chia vạch để hứng đo lượng mưa", "Loại chứa nước không đo; không tự giả định mũ nguyên trạng chống thấm."),
        entry("acoustic", "Vòm mũ cối hướng âm thanh", "hướng âm tới người nghe", "mặt phản xạ âm", "vòm lõm đổi hướng phản xạ âm", "Đặt mũ phía sau loa nhỏ để hướng âm ra phía trước", "Loại gõ mũ tạo tiếng và vai trò chứa loa đơn thuần."),
        entry("sound", "Mũ cối làm nhạc cụ gõ", "tạo nhịp bằng âm thanh", "mặt gõ", "thân mũ rung khi bị gõ", "Gõ lên mũ cối giữ nhịp bài hát", "Loại hướng âm từ nguồn khác và gõ để đóng vật."),
        entry("mold", "Mũ cối làm khuôn tạo hình", "tạo sản phẩm dạng vòm", "khuôn", "bề mặt mũ định hình vật liệu phủ lên", "Dùng mũ cối làm khuôn tạo vòm giấy bồi", "Loại kê đỡ sản phẩm sẵn có và chứa vật rời."),
    ],
}


def plan_reference(item_id, existing):
    """Tái dùng mã đã đối chiếu đúng tên; dừng nếu gặp mã bị loại/gộp hoặc xung đột."""
    from app.pipeline.dynamic_mapping import normalize_code_name
    by_name = {row.normalized_name: row for row in existing}
    plan = []
    for spec in REFERENCES[item_id]:
        names = {normalize_code_name(n) for n in [spec["name"], *spec["existing_names"]]}
        matches = [by_name[n] for n in names if n in by_name]
        if len(matches) > 1:
            raise ValueError(f"Mã tham chiếu {spec['key']} khớp nhiều mã hiện có.")
        match = matches[0] if matches else None
        if match and (match.validation_status.value != "ACCEPTED" or match.maturity_status.value != "ACTIVE"):
            raise ValueError(f"Mã {spec['key']} đã bị loại/gộp; không tự kích hoạt lại.")
        plan.append((spec, match))
    return plan


def corpus_options(item_id):
    """Thông số dùng chung với bộ nạp vỏ đạn, UUID tách theo từng đồ vật."""
    specs = REFERENCES[item_id]
    return {"item_id": item_id, "corpus": f"{item_id}-synthetic-distribution-150",
            "counts": {s["key"]: n for s, n in zip(specs, RANK_COUNTS, strict=True)},
            "variants": {s["key"]: s["illustrative_examples"] for s in specs},
            "reference_plan": lambda existing: plan_reference(item_id, existing)}
