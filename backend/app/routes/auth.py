from __future__ import annotations

import json
import secrets
from datetime import timedelta

import webauthn
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..audit import log_audit
from ..auth_utils import (
    constant_time_eq,
    create_access_token,
    generate_token,
    hash_token,
    utcnow,
)
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..rate_limit import rate_limited
from ..models import (
    AuthChallenge,
    InviteToken,
    NotificationSettings,
    Passkey,
    RecoveryToken,
    User,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/bootstrap")
def bootstrap_status(db: Session = Depends(get_db)):
    active_count = (
        db.query(func.count(User.id)).filter(User.archived_at.is_(None)).scalar()
    )
    return {"users_exist": active_count > 0}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class RegisterOptionsRequest(BaseModel):
    username: str
    email: str | None = None
    invite_token: str | None = None
    admin_secret: str | None = None


class RegisterVerifyRequest(BaseModel):
    challenge_id: str
    credential: dict


class LoginOptionsRequest(BaseModel):
    username: str | None = None


class LoginVerifyRequest(BaseModel):
    challenge_id: str
    credential: dict


class RecoveryRequest(BaseModel):
    target_user_id: str


class RecoveryOptionsRequest(BaseModel):
    recovery_token: str


class RecoveryVerifyRequest(BaseModel):
    recovery_token: str
    challenge_id: str
    credential: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_challenge(db: Session, challenge_id: str, purpose: str) -> AuthChallenge:
    challenge = db.get(AuthChallenge, challenge_id)
    if challenge is None or challenge.purpose != purpose or challenge.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid challenge"
        )
    if challenge.expires_at < utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge expired"
        )
    return challenge


def _registration_options(user_id: str, username: str, challenge: bytes) -> dict:
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user_id.encode("utf-8"),
        user_name=username,
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
            authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
        ),
    )
    return json.loads(options_to_json(options))


def _normalize_username(username: str) -> str:
    username = username.strip()
    if not username or len(username) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be 1-64 characters",
        )
    return username


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
@router.post("/register/options")
def register_options(
    body: RegisterOptionsRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limited("register")),
):
    username = _normalize_username(body.username)

    active_count = (
        db.query(func.count(User.id)).filter(User.archived_at.is_(None)).scalar()
    )

    is_admin = False
    invite_token: InviteToken | None = None

    if active_count == 0:
        if not body.admin_secret or not constant_time_eq(
            body.admin_secret, settings.admin_recovery_secret
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid admin recovery secret",
            )
        is_admin = True
    else:
        if not body.invite_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invite token required",
            )
        invite_token = (
            db.query(InviteToken)
            .filter(InviteToken.token_hash == hash_token(body.invite_token))
            .first()
        )
        if invite_token is None or invite_token.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid invite token"
            )
        if (
            invite_token.expires_at is not None
            and invite_token.expires_at < utcnow()
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invite token expired"
            )

    existing = (
        db.query(User)
        .filter(User.username == username, User.archived_at.is_(None))
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
        )

    provisional_user_id = secrets.token_hex(16)
    challenge_bytes = secrets.token_bytes(32)

    challenge = AuthChallenge(
        challenge=challenge_bytes,
        purpose="registration",
        user_id=provisional_user_id,
        username=username,
        email=body.email,
        is_admin=is_admin,
        invite_token_id=invite_token.id if invite_token else None,
        expires_at=utcnow() + timedelta(seconds=settings.challenge_ttl_seconds),
    )
    db.add(challenge)
    db.commit()

    return {
        "challenge_id": challenge.id,
        "options": _registration_options(provisional_user_id, username, challenge_bytes),
    }


@router.post("/register/verify")
def register_verify(
    body: RegisterVerifyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limited("register")),
):
    challenge = _get_challenge(db, body.challenge_id, "registration")

    try:
        verification = verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge.challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration verification failed: {exc}",
        )

    user = User(
        id=challenge.user_id,
        username=challenge.username,
        email=challenge.email,
        is_admin=challenge.is_admin,
    )
    db.add(user)
    db.flush()

    passkey = Passkey(
        user_id=user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
    )
    db.add(passkey)

    db.add(NotificationSettings(user_id=user.id))

    if challenge.invite_token_id:
        invite_token = db.get(InviteToken, challenge.invite_token_id)
        if invite_token is not None:
            invite_token.used_at = utcnow()

    challenge.used_at = utcnow()

    log_audit(
        db,
        action="user_registered",
        user_id=user.id,
        details={"username": user.username, "is_admin": user.is_admin},
    )

    db.commit()

    return {
        "user_id": user.id,
        "registered": True,
        "session_token": create_access_token(user),
        "username": user.username,
        "is_admin": user.is_admin,
    }


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
@router.post("/login/options")
def login_options(
    body: LoginOptionsRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limited("login")),
):
    allow_credentials = None
    user: User | None = None

    if body.username:
        username = body.username.strip()
        user = (
            db.query(User)
            .filter(User.username == username, User.archived_at.is_(None))
            .first()
        )
        # Do NOT return 404 for an unknown username: that leaks which accounts
        # exist (user enumeration). Instead fall through to a usernameless
        # (discoverable-credential) challenge, exactly as if no username had
        # been supplied. A valid passkey still authenticates its owner.
        if user is not None:
            passkeys = db.query(Passkey).filter(Passkey.user_id == user.id).all()
            allow_credentials = [
                PublicKeyCredentialDescriptor(id=pk.credential_id) for pk in passkeys
            ]

    challenge_bytes = secrets.token_bytes(32)
    challenge = AuthChallenge(
        challenge=challenge_bytes,
        purpose="authentication",
        user_id=user.id if user else None,
        expires_at=utcnow() + timedelta(seconds=settings.challenge_ttl_seconds),
    )
    db.add(challenge)
    db.commit()

    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        challenge=challenge_bytes,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    return {"challenge_id": challenge.id, "options": json.loads(options_to_json(options))}


@router.post("/login/verify")
def login_verify(
    body: LoginVerifyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limited("login")),
):
    challenge = _get_challenge(db, body.challenge_id, "authentication")

    raw_id = body.credential.get("rawId") or body.credential.get("id")
    try:
        credential_id = webauthn.base64url_to_bytes(raw_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credential id"
        )

    passkey = (
        db.query(Passkey).filter(Passkey.credential_id == credential_id).first()
    )
    if passkey is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown credential"
        )

    if challenge.user_id is not None and challenge.user_id != passkey.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credential does not belong to this user",
        )

    try:
        verification = verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge.challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
        )

    passkey.sign_count = verification.new_sign_count
    challenge.used_at = utcnow()

    user = db.get(User, passkey.user_id)
    if user is None or user.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User archived"
        )

    log_audit(db, action="user_logged_in", user_id=user.id)

    db.commit()

    return {
        "session_token": create_access_token(user),
        "user_id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
    }


# ---------------------------------------------------------------------------
# Recovery (admin triggered)
# ---------------------------------------------------------------------------
@router.post("/recovery")
def trigger_recovery(
    body: RecoveryRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limited("recovery")),
):
    target = db.get(User, body.target_user_id)
    if target is None or target.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    raw_token = generate_token()
    recovery_token = RecoveryToken(
        token_hash=hash_token(raw_token),
        user_id=target.id,
        created_by=admin.id,
        expires_at=utcnow()
        + timedelta(minutes=settings.recovery_token_ttl_minutes),
    )
    db.add(recovery_token)

    log_audit(
        db,
        action="recovery_triggered",
        user_id=admin.id,
        target_user_id=target.id,
    )

    db.commit()

    return {"recovery_token": raw_token, "user_id": target.id}


def _get_valid_recovery_token(db: Session, raw_token: str) -> RecoveryToken:
    recovery_token = (
        db.query(RecoveryToken)
        .filter(RecoveryToken.token_hash == hash_token(raw_token))
        .first()
    )
    if recovery_token is None or recovery_token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid recovery token"
        )
    if recovery_token.expires_at < utcnow():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Recovery token expired"
        )
    return recovery_token


@router.post("/recovery/options")
def recovery_options(
    body: RecoveryOptionsRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limited("recovery")),
):
    recovery_token = _get_valid_recovery_token(db, body.recovery_token)
    target = db.get(User, recovery_token.user_id)

    challenge_bytes = secrets.token_bytes(32)
    challenge = AuthChallenge(
        challenge=challenge_bytes,
        purpose="recovery_registration",
        user_id=target.id,
        expires_at=utcnow() + timedelta(seconds=settings.challenge_ttl_seconds),
    )
    db.add(challenge)
    db.commit()

    return {
        "challenge_id": challenge.id,
        "options": _registration_options(target.id, target.username, challenge_bytes),
    }


@router.post("/recovery/verify")
def recovery_verify(
    body: RecoveryVerifyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limited("recovery")),
):
    recovery_token = _get_valid_recovery_token(db, body.recovery_token)
    challenge = _get_challenge(db, body.challenge_id, "recovery_registration")

    if challenge.user_id != recovery_token.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge mismatch"
        )

    try:
        verification = verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge.challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration verification failed: {exc}",
        )

    passkey = Passkey(
        user_id=recovery_token.user_id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
    )
    db.add(passkey)

    recovery_token.used_at = utcnow()
    challenge.used_at = utcnow()

    log_audit(
        db,
        action="passkey_recovered",
        user_id=recovery_token.user_id,
        target_user_id=recovery_token.user_id,
    )

    db.commit()

    return {"registered": True, "user_id": recovery_token.user_id}
