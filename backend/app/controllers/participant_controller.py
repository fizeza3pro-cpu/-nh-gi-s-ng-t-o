"""Nghiệp vụ định danh participant bằng email chưa xác thực OTP."""

import hashlib
import hmac
import uuid
import secrets

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


def token_matches(participant, token: str | None) -> bool:
    """Email là định danh nghiên cứu, không phải bí mật xác thực."""
    return bool(token and participant.access_token_hash and hmac.compare_digest(
        participant.access_token_hash, hashlib.sha256(token.encode()).hexdigest(),
    ))


def _identity(participant, token: str | None = None):
    return ParticipantIdentityOut.model_validate(participant).model_copy(update={"access_token": token})


def issue_participant_token(db: Session, participant_id: str) -> ParticipantIdentityOut:
    """Cấp lại khóa cho chủ hồ sơ qua thao tác quản trị đã xác thực."""
    participant = db.get(ParticipantModel, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ.")
    token = secrets.token_urlsafe(32)
    participant.access_token_hash = hashlib.sha256(token.encode()).hexdigest()
    db.commit()
    return _identity(participant, token)


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
        if settings.participant_token_required and not token_matches(participant, payload.access_token):
            raise HTTPException(status_code=403, detail="Cần mã khôi phục hoặc trình duyệt đã tạo hồ sơ; email không đủ để truy cập hồ sơ cũ.")
        if not participant.full_name or not participant.ai_usage_group:
            return ParticipantIdentifyResult(profile_required=True)
        return ParticipantIdentifyResult(
            profile_required=False,
            participant=_identity(participant, payload.access_token),
        )

    if payload.participant_id is not None:
        legacy = db.get(ParticipantModel, str(payload.participant_id))
        if legacy is not None and legacy.email_hash is None:
            if settings.participant_token_required and not token_matches(legacy, payload.access_token):
                raise HTTPException(status_code=403, detail="Cần mã khôi phục của hồ sơ cũ.")
            legacy.email_hash = email_hash
            legacy.email_masked = _mask_email(payload.email)
            db.commit()
            db.refresh(legacy)
            if not legacy.full_name or not legacy.ai_usage_group:
                return ParticipantIdentifyResult(profile_required=True)
            return ParticipantIdentifyResult(
                profile_required=False,
                participant=_identity(legacy, payload.access_token),
            )

    return ParticipantIdentifyResult(profile_required=True)


def create_participant(db: Session, payload: ParticipantCreate) -> ParticipantIdentityOut:
    """Tạo hồ sơ theo email; gửi lại cùng email luôn nhận đúng participant cũ."""
    email_hash = _email_hash(payload.email)
    existing = db.scalar(
        select(ParticipantModel).where(ParticipantModel.email_hash == email_hash)
    )
    if existing is not None:
        if settings.participant_token_required and not token_matches(existing, payload.access_token):
            raise HTTPException(status_code=403, detail="Email đã có hồ sơ. Dùng trình duyệt cũ hoặc nhập mã khôi phục; liên hệ quản trị nếu đã mất mã.")
        # Biểu mẫu một bước đồng thời là nơi người tham gia xác nhận lại hồ sơ.
        existing.full_name = payload.full_name
        existing.age = payload.age
        existing.gender = payload.gender
        existing.occupation = payload.occupation
        existing.ai_usage_group = payload.ai_usage_group
        db.commit()
        db.refresh(existing)
        return _identity(existing, payload.access_token)

    participant_id = str(payload.participant_id or uuid.uuid4())
    existing_id = db.get(ParticipantModel, participant_id)
    if existing_id is not None:
        if settings.participant_token_required and not token_matches(existing_id, payload.access_token):
            raise HTTPException(status_code=403, detail="Cần mã khôi phục của hồ sơ cũ.")
        if existing_id.email_hash is not None and existing_id.email_hash != email_hash:
            raise HTTPException(
                status_code=409,
                detail="Thiết bị đang liên kết với một email khác.",
            )
        existing_id.email_hash = email_hash
        existing_id.email_masked = _mask_email(payload.email)
        existing_id.full_name = payload.full_name
        existing_id.age = payload.age
        existing_id.gender = payload.gender
        existing_id.occupation = payload.occupation
        existing_id.ai_usage_group = payload.ai_usage_group
        db.commit()
        db.refresh(existing_id)
        return _identity(existing_id, payload.access_token)

    token = secrets.token_urlsafe(32)
    participant = ParticipantModel(
        access_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        id=participant_id,
        full_name=payload.full_name,
        email_hash=email_hash,
        email_masked=_mask_email(payload.email),
        age=payload.age,
        gender=payload.gender,
        occupation=payload.occupation,
        ai_usage_group=payload.ai_usage_group,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return _identity(participant, token)
