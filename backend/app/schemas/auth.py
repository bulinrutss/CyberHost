from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.phone import normalize_phone, validate_phone


def _normalize_email(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


class UserCreate(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    whatsapp_ticket: str | None = Field(default=None, max_length=128)
    whatsapp_code: str | None = Field(default=None, max_length=16)
    email_ticket: str | None = Field(default=None, max_length=128)
    email_code: str | None = Field(default=None, max_length=16)

    @field_validator("phone")
    @classmethod
    def normalize_user_phone(cls, value: str) -> str:
        return validate_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_user_email(cls, value: object) -> object:
        return _normalize_email(value)


class UserLogin(BaseModel):
    username: str = Field(min_length=3, max_length=254)
    password: str

    @field_validator("username")
    @classmethod
    def normalize_login_username(cls, value: str) -> str:
        text = value.strip()
        if "@" in text:
            return text.lower()
        return normalize_phone(text)


class UserResponse(BaseModel):
    id: int
    phone: str
    email: str | None = None
    name: str
    is_active: bool
    is_admin: bool
    mfa_enabled: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    is_admin: bool = False

    @field_validator("phone")
    @classmethod
    def normalize_admin_phone(cls, value: str) -> str:
        return validate_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_admin_email(cls, value: object) -> object:
        return _normalize_email(value)


class AdminUserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    reset_mfa: bool | None = None


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=20)
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)
    whatsapp_ticket: str | None = Field(default=None, max_length=128)
    whatsapp_code: str | None = Field(default=None, max_length=16)
    email_ticket: str | None = Field(default=None, max_length=128)
    email_code: str | None = Field(default=None, max_length=16)

    @field_validator("phone")
    @classmethod
    def normalize_profile_phone(cls, value: str) -> str:
        return validate_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_profile_email(cls, value: object) -> object:
        return _normalize_email(value)

    @field_validator("new_password", mode="before")
    @classmethod
    def empty_new_password(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value


class Token(BaseModel):
    access_token: str = ""
    token_type: str = "bearer"
    authenticated: bool = False
    mfa_required: bool = False
    mfa_setup_required: bool = False
    mfa_ticket: str | None = None
    mfa_secret: str | None = None
    otpauth_url: str | None = None


class MfaVerifyPayload(BaseModel):
    ticket: str = Field(min_length=16, max_length=128)
    code: str = Field(min_length=6, max_length=16)


class MfaSetupStartPayload(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class MfaSetupStartResponse(BaseModel):
    mfa_ticket: str
    mfa_secret: str
    otpauth_url: str


class MfaSetupConfirmPayload(BaseModel):
    ticket: str = Field(min_length=16, max_length=128)
    code: str = Field(min_length=6, max_length=16)


class MfaDisablePayload(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=16)


class StepUpRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=16)


class StepUpResponse(BaseModel):
    step_up_token: str
    expires_in: int
    mfa_enabled: bool


class AuthSessionItem(BaseModel):
    id: int
    device_id: str
    user_agent: str
    ip: str
    created_at: datetime
    last_seen_at: datetime
    current: bool


class PasskeyLoginOptionsPayload(BaseModel):
    username: str = Field(min_length=3, max_length=254)

    @field_validator("username")
    @classmethod
    def normalize_passkey_username(cls, value: str) -> str:
        text = value.strip()
        if "@" in text:
            return text.lower()
        return normalize_phone(text)


class PasskeyRegisterVerifyPayload(BaseModel):
    credential: dict | str
    device_name: str | None = Field(default=None, max_length=120)


class PasskeyLoginVerifyPayload(BaseModel):
    username: str = Field(min_length=3, max_length=254)
    credential: dict | str

    @field_validator("username")
    @classmethod
    def normalize_passkey_login_username(cls, value: str) -> str:
        text = value.strip()
        if "@" in text:
            return text.lower()
        return normalize_phone(text)


class PasskeyItem(BaseModel):
    id: int
    device_name: str
    created_at: datetime
    last_used_at: datetime | None = None


class PhoneVerificationStatus(BaseModel):
    required: bool
    channel: str | None = None


class WhatsAppSendPayload(BaseModel):
    phone: str = Field(min_length=10, max_length=20)

    @field_validator("phone")
    @classmethod
    def normalize_otp_phone(cls, value: str) -> str:
        return validate_phone(value)


class WhatsAppSendResponse(BaseModel):
    ticket: str
    expires_in: int
    retry_after: int


class EmailSendPayload(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_otp_email(cls, value: object) -> object:
        return _normalize_email(value)
