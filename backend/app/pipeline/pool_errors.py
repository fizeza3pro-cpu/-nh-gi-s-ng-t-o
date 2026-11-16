"""Lỗi vận hành quota phải đi thẳng tới worker, không biến thành mơ hồ ngữ nghĩa."""


class ModelPoolWait(RuntimeError):
    def __init__(self, reason="NO_MODEL_CAPACITY"):
        super().__init__("Đang chờ model BytePlus khả dụng; bài đã lưu được giữ nguyên.")
        self.metadata = {"error_category": "MODEL_POOL_WAIT", "retryable": True, "wait_reason": reason}


class ModelPoolChanged(RuntimeError):
    """Model đang giữ cho nhóm scoring không còn dùng được; phải bỏ nhóm chưa chốt."""

    def __init__(self, slot):
        super().__init__("Cần chạy lại nhóm scoring bằng cùng một model mới.")
        self.slot = slot
