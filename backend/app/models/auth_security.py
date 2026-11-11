from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuthThrottle(Base):
    """Contador compartilhado entre workers para login/registro/MFA."""

    __tablename__ = "auth_throttle"
    __table_args__ = (
        UniqueConstraint("scope", "key_value", name="uq_auth_throttle_scope_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    key_value: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(DateTime)
    count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuthMfaTicket(Base):
    """Ticket curto de desafio/enrolamento MFA (uso único)."""

    __tablename__ = "auth_mfa_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    purpose: Mapped[str] = mapped_column(String(16), index=True)
    pending_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthStepUpTicket(Base):
    """Confirmação reutilizável (senha + MFA opcional) para ações sensíveis."""

    __tablename__ = "auth_step_up_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthPhoneChallenge(Base):
    """OTP de WhatsApp para confirmar telefone no cadastro/perfil."""

    __tablename__ = "auth_phone_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    purpose: Mapped[str] = mapped_column(String(16), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthEmailChallenge(Base):
    """OTP de e-mail para confirmar endereço no cadastro/perfil."""

    __tablename__ = "auth_email_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    purpose: Mapped[str] = mapped_column(String(16), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthSession(Base):
    """Sessão opaca no banco (access + refresh rotativo, revogável)."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    access_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    refresh_family: Mapped[str] = mapped_column(String(64), index=True)
    device_id: Mapped[str] = mapped_column(String(128), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class WebAuthnCredential(Base):
    """Passkeys / WebAuthn cadastradas pelo usuário."""

    __tablename__ = "webauthn_credentials"
    __table_args__ = (UniqueConstraint("credential_id", name="uq_webauthn_credential_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    credential_id: Mapped[str] = mapped_column(String(512), nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    transports: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_name: Mapped[str] = mapped_column(String(120), default="Passkey")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuthWebAuthnChallenge(Base):
    """Desafio WebAuthn de curta duração (registro/login)."""

    __tablename__ = "auth_webauthn_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(16), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
