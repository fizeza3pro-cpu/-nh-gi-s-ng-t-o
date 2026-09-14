"""Nghiệp vụ định danh participant bằng email chưa xác thực OTP."""

import hashlib
import hmac
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Participant as ParticipantModel
from app.schemas.schemas import (
    ParticipantCreate,
    ParticipantIdentify,
    ParticipantIdentifyResult,
    ParticipantIdentityOut,
)


def _email_hash(email: str) -> str:
    """Tạo khoá tra cứu email nhưng không lưu email rõ trong database."""
    secret = (settings.participant_email_secret or settings.jwt_secret).encode("utf-8")
    return hmac.new(secret, email.encode("utf-8"), hashlib.sha256).hexdigest()


def _mask_email(email: str) -> str:
    """Giữ một gợi ý không nhạy cảm để admin phân biệt hồ sơ."""
    local, domain = email.split("@", 1)
    visible = local[:2] if len(local) > 1 else local[:1]
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"


def identify_participant(
    db: Session, payload: ParticipantIdentify
) -> ParticipantIdentifyResult:
    """Tìm participant theo email hoặc gắn email cho hồ sơ UUID cũ trên cùng trình duyệt."""
    email_hash = _email_hash(payload.email)
    participant = db.scalar(
        select(ParticipantModel).where(ParticipantModel.email_hash == email_hash)
    )
    if participant is not None:
        if not participant.full_name:
            return ParticipantIdentifyResult(profile_required=True)
        return ParticipantIdentifyResult(
            profile_required=False,
            participant=ParticipantIdentityOut.model_validate(participant),
        )

    if payload.participant_id is not None:
        legacy = db.get(ParticipantModel, str(payload.participant_id))
        if legacy is not None and legacy.email_hash is None:
            legacy.email_hash = email_hash
            legacy.email_masked = _mask_email(payload.email)
            db.commit()
            db.refresh(legacy)
            if not legacy.full_name:
                return ParticipantIdentifyResult(profile_required=True)
            return ParticipantIdentifyResult(
                profile_required=False,
                participant=ParticipantIdentityOut.model_validate(legacy),
            )

    return ParticipantIdentifyResult(profile_required=True)


def create_participant(db: Session, payload: ParticipantCreate) -> ParticipantIdentityOut:
    """Tạo hồ sơ theo email; gửi lại cùng email luôn nhận đúng participant cũ."""
    email_hash = _email_hash(payload.email)
    existing = db.scalar(
        select(ParticipantModel).where(ParticipantModel.email_hash == email_hash)
    )
    if existing is not None:
        # Hồ sơ tạo trước migration chưa có họ tên: cho phép bổ sung đúng một lần,
        # đồng thời chỉ lấp các trường nhân khẩu học còn thiếu.
        if not existing.full_name:
            existing.full_name = payload.full_name
            existing.age = existing.age if existing.age is not None else payload.age
            existing.gender = existing.gender or payload.gender
            existing.occupation = existing.occupation or payload.occupation
            db.commit()
            db.refresh(existing)
        return ParticipantIdentityOut.model_validate(existing)

    participant_id = str(payload.participant_id or uuid.uuid4())
    existing_id = db.get(ParticipantModel, participant_id)
    if existing_id is not None:
        if existing_id.email_hash is not None and existing_id.email_hash != email_hash:
            raise HTTPException(
                status_code=409,
                detail="Thiết bị đang liên kết với một email khác.",
            )
        existing_id.email_hash = email_hash
        existing_id.email_masked = _mask_email(payload.email)
        existing_id.full_name = payload.full_name
        existing_id.age = existing_id.age if existing_id.age is not None else payload.age
        existing_id.gender = existing_id.gender or payload.gender
        existing_id.occupation = existing_id.occupation or payload.occupation
        db.commit()
        db.refresh(existing_id)
        return ParticipantIdentityOut.model_validate(existing_id)

    participant = ParticipantModel(
        id=participant_id,
        full_name=payload.full_name,
        email_hash=email_hash,
        email_masked=_mask_email(payload.email),
        age=payload.age,
        gender=payload.gender,
        occupation=payload.occupation,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return ParticipantIdentityOut.model_validate(participant)
