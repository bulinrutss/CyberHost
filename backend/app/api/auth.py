from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import attach_session, clear_session_cookie, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthSessionItem,
    EmailSendPayload,
    MfaDisablePayload,
    MfaSetupConfirmPayload,
    MfaSetupStartPayload,
    MfaSetupStartResponse,
    MfaVerifyPayload,
    PasskeyItem,
    PasskeyLoginOptionsPayload,
    PasskeyLoginVerifyPayload,
    PasskeyRegisterVerifyPayload,
    PhoneVerificationStatus,
    ProfileUpdate,
    StepUpRequest,
    StepUpResponse,
    Token,
    UserCreate,
    UserResponse,
    WhatsAppSendPayload,
    WhatsAppSendResponse,
)
from app.services import (
    admin_mfa,
    auth_sessions,
    auth_step_up,
    auth_throttle,
    email_otp,
    phone_otp,
    webauthn_passkeys,
)
from app.services.totp import generate_secret, otpauth_url, verify_totp
from app.utils.phone import normalize_phone, validate_phone

router = APIRouter()

_DUMMY_HASH: str | None = None
LOGIN_FAILED = "Telefone, e-mail ou senha incorretos"


def _dummy_password_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("!")
    return _DUMMY_HASH


def _login_identifier(raw: str) -> tuple[str, str]:
    value = (raw or "").strip()
    if "@" in value:
        return "email", value.lower()
    return "phone", normalize_phone(value)


def _find_user_by_login(db: Session, kind: str, ident: str) -> User | None:
    if not ident:
        return None
    if kind == "email":
        return db.query(User).filter(User.email == ident).first()
    return db.query(User).filter(User.phone == ident).first()


def _send_whatsapp_code(
    payload: WhatsAppSendPayload,
    request: Request,
    db: Session,
    *,
    purpose: str,
    exclude_user_id: int | None,
) -> WhatsAppSendResponse:
    ip = auth_throttle.client_ip(request)
    phone = validate_phone(payload.phone)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.WHATSAPP_SEND_IP_SCOPE, ip),
        auth_throttle.check_lock(db, auth_throttle.WHATSAPP_SEND_PHONE_SCOPE, phone),
    )
    ticket, ttl, cooldown = phone_otp.issue_challenge(
        db,
        phone=phone,
        purpose=purpose,
        exclude_user_id=exclude_user_id,
    )
    auth_throttle.raise_if_limited(
        auth_throttle.add_hit(
            db, auth_throttle.WHATSAPP_SEND_IP_SCOPE, ip, ip=ip, failed=False
        ),
        auth_throttle.add_hit(
            db, auth_throttle.WHATSAPP_SEND_PHONE_SCOPE, phone, ip=ip, failed=False
        ),
    )
    return WhatsAppSendResponse(ticket=ticket, expires_in=ttl, retry_after=cooldown)


@router.get("/phone-verification", response_model=PhoneVerificationStatus)
def phone_verification_status():
    required = phone_otp.verification_required()
    return PhoneVerificationStatus(
        required=required,
        channel="whatsapp" if required else None,
    )


@router.post("/whatsapp/send", response_model=WhatsAppSendResponse)
def send_whatsapp_code_register(
    payload: WhatsAppSendPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    return _send_whatsapp_code(
        payload,
        request,
        db,
        purpose=phone_otp.PURPOSE_REGISTER,
        exclude_user_id=None,
    )


@router.post("/whatsapp/send-profile", response_model=WhatsAppSendResponse)
def send_whatsapp_code_profile(
    payload: WhatsAppSendPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _send_whatsapp_code(
        payload,
        request,
        db,
        purpose=phone_otp.PURPOSE_PROFILE,
        exclude_user_id=user.id,
    )


def _send_email_code(
    payload: EmailSendPayload,
    request: Request,
    db: Session,
    *,
    purpose: str,
    exclude_user_id: int | None,
) -> WhatsAppSendResponse:
    ip = auth_throttle.client_ip(request)
    email = str(payload.email)
    email_key = email_otp.throttle_key(email)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.EMAIL_SEND_IP_SCOPE, ip),
        auth_throttle.check_lock(db, auth_throttle.EMAIL_SEND_SCOPE, email_key),
    )
    ticket, ttl, cooldown = email_otp.issue_challenge(
        db,
        email=email,
        purpose=purpose,
        exclude_user_id=exclude_user_id,
    )
    auth_throttle.raise_if_limited(
        auth_throttle.add_hit(
            db, auth_throttle.EMAIL_SEND_IP_SCOPE, ip, ip=ip, failed=False
        ),
        auth_throttle.add_hit(
            db, auth_throttle.EMAIL_SEND_SCOPE, email_key, ip=ip, failed=False
        ),
    )
    return WhatsAppSendResponse(ticket=ticket, expires_in=ttl, retry_after=cooldown)


@router.get("/email-verification", response_model=PhoneVerificationStatus)
def email_verification_status():
    required = email_otp.verification_required()
    return PhoneVerificationStatus(
        required=required,
        channel="email" if required else None,
    )


@router.post("/email/send", response_model=WhatsAppSendResponse)
def send_email_code_register(
    payload: EmailSendPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    return _send_email_code(
        payload,
        request,
        db,
        purpose=email_otp.PURPOSE_REGISTER,
        exclude_user_id=None,
    )


@router.post("/email/send-profile", response_model=WhatsAppSendResponse)
def send_email_code_profile(
    payload: EmailSendPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _send_email_code(
        payload,
        request,
        db,
        purpose=email_otp.PURPOSE_PROFILE,
        exclude_user_id=user.id,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.REGISTER_IP_SCOPE, ip)
    )
    phone = validate_phone(payload.phone)
    email = str(payload.email)
    existing = db.query(User).filter(User.phone == phone).first()
    email_taken = db.query(User).filter(User.email == email).first()
    retry = auth_throttle.add_hit(
        db, auth_throttle.REGISTER_IP_SCOPE, ip, ip=ip, failed=False
    )
    if existing:
        auth_throttle.raise_if_limited(retry)
        raise HTTPException(status_code=400, detail="Telefone já cadastrado")
    if email_taken:
        auth_throttle.raise_if_limited(retry)
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    auth_throttle.raise_if_limited(retry)

    if phone_otp.verification_required():
        auth_throttle.raise_if_limited(
            auth_throttle.check_lock(db, auth_throttle.WHATSAPP_VERIFY_PHONE_SCOPE, phone)
        )
        try:
            phone_otp.consume_challenge(
                db,
                ticket=payload.whatsapp_ticket or "",
                code=payload.whatsapp_code or "",
                phone=phone,
                purpose=phone_otp.PURPOSE_REGISTER,
            )
        except HTTPException as exc:
            if exc.status_code in {400, 429}:
                auth_throttle.raise_if_limited(
                    auth_throttle.add_hit(
                        db,
                        auth_throttle.WHATSAPP_VERIFY_PHONE_SCOPE,
                        phone,
                        ip=ip,
                        failed=True,
                    )
                )
            raise
        auth_throttle.reset_bucket(db, auth_throttle.WHATSAPP_VERIFY_PHONE_SCOPE, phone)

    if email_otp.verification_required():
        email_key = email_otp.throttle_key(email)
        auth_throttle.raise_if_limited(
            auth_throttle.check_lock(db, auth_throttle.EMAIL_VERIFY_SCOPE, email_key)
        )
        try:
            email_otp.consume_challenge(
                db,
                ticket=payload.email_ticket or "",
                code=payload.email_code or "",
                email=email,
                purpose=email_otp.PURPOSE_REGISTER,
            )
        except HTTPException as exc:
            if exc.status_code in {400, 429}:
                auth_throttle.raise_if_limited(
                    auth_throttle.add_hit(
                        db,
                        auth_throttle.EMAIL_VERIFY_SCOPE,
                        email_key,
                        ip=ip,
                        failed=True,
                    )
                )
            raise
        auth_throttle.reset_bucket(db, auth_throttle.EMAIL_VERIFY_SCOPE, email_key)

    user = User(
        phone=phone,
        email=email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip = auth_throttle.client_ip(request)
    kind, ident = _login_identifier(form.username)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.LOGIN_IP_SCOPE, ip),
        auth_throttle.check_lock(db, auth_throttle.LOGIN_PHONE_SCOPE, ident or "empty"),
    )

    user = _find_user_by_login(db, kind, ident)
    hashed = user.hashed_password if user is not None else _dummy_password_hash()
    valid = verify_password(form.password, hashed)
    if user is None or not user.is_active or not valid:
        auth_throttle.raise_if_limited(
            auth_throttle.add_hit(db, auth_throttle.LOGIN_IP_SCOPE, ip, ip=ip, failed=True),
            auth_throttle.add_hit(
                db, auth_throttle.LOGIN_PHONE_SCOPE, ident or "empty", ip=ip, failed=True
            ),
        )
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)

    auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, ident)
    if user.phone:
        auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone)
    if user.email:
        auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, user.email)
    auth_throttle.raise_if_limited(
        auth_throttle.add_hit(db, auth_throttle.LOGIN_IP_SCOPE, ip, ip=ip, failed=False)
    )

    if user.is_admin and admin_mfa.required():
        clear_session_cookie(response, request)
        return Token(**admin_mfa.start_admin_login(db, user))
    if user.mfa_enabled:
        clear_session_cookie(response, request)
        ticket, _ttl, _ = admin_mfa.issue_mfa_ticket(
            db, user, admin_mfa.PURPOSE_CHALLENGE
        )
        return Token(
            authenticated=False,
            mfa_required=True,
            mfa_ticket=ticket,
        )
    attach_session(response, user.id, request, db=db)
    return Token(authenticated=True)


@router.post("/mfa/verify", response_model=Token)
def verify_mfa(
    payload: MfaVerifyPayload,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.MFA_IP_SCOPE, ip)
    )
    try:
        user = admin_mfa.redeem_mfa_ticket(db, payload.ticket, payload.code)
    except HTTPException as exc:
        if exc.status_code == 401:
            auth_throttle.raise_if_limited(
                auth_throttle.add_hit(
                    db, auth_throttle.MFA_IP_SCOPE, ip, ip=ip, failed=True
                )
            )
        raise
    auth_throttle.reset_bucket(db, auth_throttle.MFA_IP_SCOPE, ip)
    auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone)
    if user.email:
        auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, user.email)
    attach_session(response, user.id, request, db=db)
    return Token(authenticated=True)


@router.post("/mfa/setup/start", response_model=MfaSetupStartResponse)
def mfa_setup_start(
    payload: MfaSetupStartPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.LOGIN_IP_SCOPE, ip),
        auth_throttle.check_lock(db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone),
    )
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA já está ativado")
    if not verify_password(payload.password, user.hashed_password):
        auth_throttle.raise_if_limited(
            auth_throttle.add_hit(db, auth_throttle.LOGIN_IP_SCOPE, ip, ip=ip, failed=True),
            auth_throttle.add_hit(
                db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone, ip=ip, failed=True
            ),
        )
        raise HTTPException(status_code=403, detail="Senha atual incorreta")
    auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone)
    secret = generate_secret()
    ticket, _ttl, otpauth = admin_mfa.issue_mfa_ticket(
        db, user, admin_mfa.PURPOSE_ENROLL, pending_secret=secret
    )
    return MfaSetupStartResponse(
        mfa_ticket=ticket,
        mfa_secret=secret,
        otpauth_url=otpauth or otpauth_url(secret, user.phone),
    )


@router.post("/mfa/setup/confirm", response_model=UserResponse)
def mfa_setup_confirm(
    payload: MfaSetupConfirmPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.MFA_IP_SCOPE, ip)
    )
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA já está ativado")
    try:
        enrolled = admin_mfa.redeem_mfa_ticket(
            db,
            payload.ticket,
            payload.code,
            expected_user_id=user.id,
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            auth_throttle.raise_if_limited(
                auth_throttle.add_hit(
                    db, auth_throttle.MFA_IP_SCOPE, ip, ip=ip, failed=True
                )
            )
        raise
    auth_throttle.reset_bucket(db, auth_throttle.MFA_IP_SCOPE, ip)
    db.refresh(enrolled)
    return enrolled


@router.post("/mfa/disable", response_model=UserResponse)
def mfa_disable(
    payload: MfaDisablePayload,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.LOGIN_IP_SCOPE, ip),
        auth_throttle.check_lock(db, auth_throttle.MFA_IP_SCOPE, ip),
    )
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA não está ativado")
    if not verify_password(payload.password, user.hashed_password):
        auth_throttle.raise_if_limited(
            auth_throttle.add_hit(db, auth_throttle.LOGIN_IP_SCOPE, ip, ip=ip, failed=True),
        )
        raise HTTPException(status_code=403, detail="Senha atual incorreta")
    plain = admin_mfa.decrypt_secret(user.mfa_secret)
    if not verify_totp(plain, payload.code):
        auth_throttle.raise_if_limited(
            auth_throttle.add_hit(db, auth_throttle.MFA_IP_SCOPE, ip, ip=ip, failed=True)
        )
        raise HTTPException(status_code=401, detail="Código MFA inválido")
    admin_mfa.clear_mfa(user)
    db.commit()
    db.refresh(user)
    auth_throttle.reset_bucket(db, auth_throttle.MFA_IP_SCOPE, ip)
    return user


@router.post("/step-up", response_model=StepUpResponse)
def step_up(
    payload: StepUpRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw, ttl = auth_step_up.issue_step_up(
        db, user, payload.password, mfa_code=payload.mfa_code
    )
    return StepUpResponse(
        step_up_token=raw,
        expires_in=ttl,
        mfa_enabled=bool(user.mfa_enabled),
    )


@router.post("/refresh", response_model=Token)
def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    auth_sessions.rotate_refresh(db, request, response)
    return Token(authenticated=True)


@router.get("/sessions", response_model=list[AuthSessionItem])
def list_auth_sessions(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return auth_sessions.list_sessions(db, user.id, request)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_auth_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    auth_sessions.revoke_session(db, user.id, session_id)


@router.post("/sessions/revoke-others")
def revoke_other_sessions(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = auth_sessions.revoke_all_sessions(db, user.id, keep_current=request)
    return {"revoked": count}


@router.post("/passkey/register/options")
def passkey_register_options(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return webauthn_passkeys.registration_options(db, user)


@router.post("/passkey/register/verify", response_model=PasskeyItem)
def passkey_register_verify(
    payload: PasskeyRegisterVerifyPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = webauthn_passkeys.verify_registration(
        db,
        user,
        payload.credential,
        device_name=payload.device_name,
    )
    return PasskeyItem(
        id=row.id,
        device_name=row.device_name,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


@router.post("/passkey/login/options")
def passkey_login_options(
    payload: PasskeyLoginOptionsPayload,
    db: Session = Depends(get_db),
):
    return webauthn_passkeys.login_options(db, payload.username)


@router.post("/passkey/login/verify", response_model=Token)
def passkey_login_verify(
    payload: PasskeyLoginVerifyPayload,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.LOGIN_IP_SCOPE, ip),
    )
    try:
        user = webauthn_passkeys.verify_login(db, payload.username, payload.credential)
    except HTTPException as exc:
        if exc.status_code in {400, 401}:
            auth_throttle.raise_if_limited(
                auth_throttle.add_hit(
                    db, auth_throttle.LOGIN_IP_SCOPE, ip, ip=ip, failed=True
                )
            )
        raise
    auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone)
    if user.email:
        auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, user.email)
    attach_session(response, user.id, request, db=db)
    return Token(authenticated=True)


@router.get("/passkeys", response_model=list[PasskeyItem])
def list_passkeys(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return webauthn_passkeys.list_passkeys(db, user.id)


@router.delete("/passkeys/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_passkey(
    credential_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    webauthn_passkeys.delete_passkey(db, user.id, credential_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    auth_sessions.revoke_request_session(db, request)
    clear_session_cookie(response, request)


@router.get("/me", response_model=UserResponse)
def me(response: Response, user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return user


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: ProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.LOGIN_IP_SCOPE, ip),
        auth_throttle.check_lock(db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone),
    )
    if not verify_password(payload.current_password, user.hashed_password):
        auth_throttle.raise_if_limited(
            auth_throttle.add_hit(db, auth_throttle.LOGIN_IP_SCOPE, ip, ip=ip, failed=True),
            auth_throttle.add_hit(
                db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone, ip=ip, failed=True
            ),
        )
        raise HTTPException(status_code=403, detail="Senha atual incorreta")

    auth_throttle.reset_bucket(db, auth_throttle.LOGIN_PHONE_SCOPE, user.phone)

    phone = payload.phone
    email = str(payload.email)
    if phone != user.phone:
        taken = (
            db.query(User)
            .filter(User.phone == phone, User.id != user.id)
            .first()
        )
        if taken:
            raise HTTPException(status_code=400, detail="Telefone já cadastrado")
        if phone_otp.verification_required():
            auth_throttle.raise_if_limited(
                auth_throttle.check_lock(
                    db, auth_throttle.WHATSAPP_VERIFY_PHONE_SCOPE, phone
                )
            )
            try:
                phone_otp.consume_challenge(
                    db,
                    ticket=payload.whatsapp_ticket or "",
                    code=payload.whatsapp_code or "",
                    phone=phone,
                    purpose=phone_otp.PURPOSE_PROFILE,
                )
            except HTTPException as exc:
                if exc.status_code in {400, 429}:
                    auth_throttle.raise_if_limited(
                        auth_throttle.add_hit(
                            db,
                            auth_throttle.WHATSAPP_VERIFY_PHONE_SCOPE,
                            phone,
                            ip=ip,
                            failed=True,
                        )
                    )
                raise
            auth_throttle.reset_bucket(
                db, auth_throttle.WHATSAPP_VERIFY_PHONE_SCOPE, phone
            )
    if email != (user.email or ""):
        taken = (
            db.query(User)
            .filter(User.email == email, User.id != user.id)
            .first()
        )
        if taken:
            raise HTTPException(status_code=400, detail="E-mail já cadastrado")
        if email_otp.verification_required():
            email_key = email_otp.throttle_key(email)
            auth_throttle.raise_if_limited(
                auth_throttle.check_lock(db, auth_throttle.EMAIL_VERIFY_SCOPE, email_key)
            )
            try:
                email_otp.consume_challenge(
                    db,
                    ticket=payload.email_ticket or "",
                    code=payload.email_code or "",
                    email=email,
                    purpose=email_otp.PURPOSE_PROFILE,
                )
            except HTTPException as exc:
                if exc.status_code in {400, 429}:
                    auth_throttle.raise_if_limited(
                        auth_throttle.add_hit(
                            db,
                            auth_throttle.EMAIL_VERIFY_SCOPE,
                            email_key,
                            ip=ip,
                            failed=True,
                        )
                    )
                raise
            auth_throttle.reset_bucket(db, auth_throttle.EMAIL_VERIFY_SCOPE, email_key)

    user.name = payload.name
    user.phone = phone
    user.email = email
    if payload.new_password:
        user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return user
