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
from ..models import (
    AuthChallenge,
    InviteToken,
    NotificationSettings,
    Passkey,
    RecoveryToken,
    User,
)
from ..rate_limit import enforce_auth_rate_limit

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
    # Optional user-chosen label for this passkey (e.g. "iPhone", "YubiKey").
    # Falls back to a device-type-based default when omitted.
    passkey_name: str | None = None


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


class AddPasskeyVerifyRequest(BaseModel):
    challenge_id: str
    credential: dict
    passkey_name: str | None = None


class RemovePasskeyVerifyRequest(BaseModel):
    challenge_id: str
    credential: dict


class RenamePasskeyRequest(BaseModel):
    name: str


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
            # No authenticator_attachment restriction: allow both platform
            # authenticators (Face ID, Touch ID, Windows Hello) and
            # cross-platform ones (YubiKey, other security keys). The
            # previous CROSS_PLATFORM-only setting silently excluded phone/
            # OS-level passkeys, which is the opposite of what usernameless
            # login needs - the whole point is the browser showing every
            # passkey the user has, not just external keys.
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


def _default_passkey_name(device_type: object, requested: str | None) -> str:
    if requested:
        name = requested.strip()
        if name:
            return name[:100]
    # CredentialDeviceType.MULTI_DEVICE means a synced/platform passkey
    # (Face ID, Touch ID, Windows Hello, Google Password Manager, ...) -
    # SINGLE_DEVICE means a bound authenticator (security key). Neither
    # tells us the exact device model without an AAGUID lookup database,
    # which is more complexity than this needs; the user can always rename
    # it from the passkey management UI afterwards.
    value = getattr(device_type, "value", str(device_type))
    return "Passkey (this device)" if value == "multi_device" else "Security key"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
@router.post("/register/options")
def register_options(
    body: RegisterOptionsRequest,
    db: Session = Depends(get_db),
    _rl: None = Depends(enforce_auth_rate_limit),
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
    _rl: None = Depends(enforce_auth_rate_limit),
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
        name=_default_passkey_name(verification.credential_device_type, body.passkey_name),
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
    _rl: None = Depends(enforce_auth_rate_limit),
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
        # Deliberately NOT raising 404 when the username doesn't exist: doing
        # so lets anyone on the network enumerate valid usernames just by
        # probing this endpoint, with no authentication required. Instead we
        # fall through to the same discoverable-credential challenge shape
        # used when no username is given at all - the browser's passkey
        # prompt looks identical either way, and login/verify still rejects
        # the attempt on its own merits.
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
    _rl: None = Depends(enforce_auth_rate_limit),
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
    passkey.last_used_at = utcnow()
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
    _rl: None = Depends(enforce_auth_rate_limit),
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
    _rl: None = Depends(enforce_auth_rate_limit),
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
        name=_default_passkey_name(verification.credential_device_type, None),
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


# ---------------------------------------------------------------------------
# Passkey management (logged-in user manages their own passkeys)
# ---------------------------------------------------------------------------
@router.get("/passkeys")
def list_passkeys(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    passkeys = (
        db.query(Passkey)
        .filter(Passkey.user_id == user.id)
        .order_by(Passkey.created_at.asc())
        .all()
    )
    return [
        {
            "id": pk.id,
            "name": pk.name,
            "created_at": pk.created_at.isoformat(),
            "last_used_at": pk.last_used_at.isoformat() if pk.last_used_at else None,
        }
        for pk in passkeys
    ]


@router.post("/passkeys/add/options")
def add_passkey_options(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(enforce_auth_rate_limit),
):
    """Start adding an additional passkey to the currently logged-in user.

    Unlike initial registration, this requires an existing valid session
    (get_current_user) - you can't use this to register a brand new
    account, only to attach one more credential to the account you're
    already authenticated as.
    """
    challenge_bytes = secrets.token_bytes(32)
    challenge = AuthChallenge(
        challenge=challenge_bytes,
        purpose="add_passkey",
        user_id=user.id,
        username=user.username,
        expires_at=utcnow() + timedelta(seconds=settings.challenge_ttl_seconds),
    )
    db.add(challenge)
    db.commit()

    return {
        "challenge_id": challenge.id,
        "options": _registration_options(user.id, user.username, challenge_bytes),
    }


@router.post("/passkeys/add/verify")
def add_passkey_verify(
    body: AddPasskeyVerifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(enforce_auth_rate_limit),
):
    challenge = _get_challenge(db, body.challenge_id, "add_passkey")
    if challenge.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Challenge does not belong to this user"
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
        user_id=user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        name=_default_passkey_name(verification.credential_device_type, body.passkey_name),
    )
    db.add(passkey)
    challenge.used_at = utcnow()

    log_audit(db, action="passkey_added", user_id=user.id)

    db.commit()

    return {"id": passkey.id, "name": passkey.name}


@router.post("/passkeys/{passkey_id}/remove/options")
def remove_passkey_options(
    passkey_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(enforce_auth_rate_limit),
):
    """Start removing a passkey - requires authenticating with THAT SPECIFIC
    passkey as confirmation, not just the current session. This is
    deliberate: a stolen/leaked session token alone should never be enough
    to strip a user's other passkeys - the removal has to be proven with
    the credential being removed itself, which only the legitimate device
    owner can produce.
    """
    target = db.get(Passkey, passkey_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found"
        )

    challenge_bytes = secrets.token_bytes(32)
    challenge = AuthChallenge(
        challenge=challenge_bytes,
        purpose="remove_passkey",
        user_id=user.id,
        expires_at=utcnow() + timedelta(seconds=settings.challenge_ttl_seconds),
    )
    db.add(challenge)
    db.commit()

    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        challenge=challenge_bytes,
        allow_credentials=[PublicKeyCredentialDescriptor(id=target.credential_id)],
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    return {"challenge_id": challenge.id, "options": json.loads(options_to_json(options))}


@router.post("/passkeys/{passkey_id}/remove/verify")
def remove_passkey_verify(
    passkey_id: str,
    body: RemovePasskeyVerifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(enforce_auth_rate_limit),
):
    challenge = _get_challenge(db, body.challenge_id, "remove_passkey")
    if challenge.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Challenge does not belong to this user"
        )

    target = db.get(Passkey, passkey_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found"
        )

    raw_id = body.credential.get("rawId") or body.credential.get("id")
    try:
        credential_id = webauthn.base64url_to_bytes(raw_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credential id"
        )

    # The credential presented must be the SAME one being removed - proves
    # the requester actually holds this specific passkey, not just any
    # passkey belonging to the account.
    if credential_id != target.credential_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must authenticate with the passkey being removed",
        )

    remaining_count = (
        db.query(func.count(Passkey.id)).filter(Passkey.user_id == user.id).scalar()
    )
    if remaining_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove your last passkey - you would be locked out",
        )

    try:
        verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge.challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=target.public_key,
            credential_current_sign_count=target.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
        )

    challenge.used_at = utcnow()
    db.delete(target)

    log_audit(db, action="passkey_removed", user_id=user.id)

    db.commit()

    return {"removed": True, "id": passkey_id}


@router.patch("/passkeys/{passkey_id}")
def rename_passkey(
    passkey_id: str,
    body: RenamePasskeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.get(Passkey, passkey_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found"
        )
    name = body.name.strip()
    if not name or len(name) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name must be 1-100 characters",
        )
    target.name = name
    db.commit()
    return {"id": target.id, "name": target.name}
