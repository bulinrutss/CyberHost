from pydantic import BaseModel, Field, field_validator


class HostPushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=64)


class HostPushSubscribe(BaseModel):
    endpoint: str = Field(min_length=20, max_length=768)
    keys: HostPushKeys

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        endpoint = value.strip()
        if not endpoint.startswith("https://"):
            raise ValueError("Inscrição inválida")
        return endpoint


class HostPushMeta(BaseModel):
    vapid_public_key: str | None = None
    push_available: bool = False
