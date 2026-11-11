from typing import Self
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _origin_from_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return url.strip().rstrip("/")


def _is_https_url(url: str) -> bool:
    return url.strip().lower().startswith("https://")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "VPS Host Panel"
    app_environment: str = "development"
    secret_key: str = "dev-secret-change-in-production"
    database_url: str = "mysql+pymysql://root@127.0.0.1:3306/vps_host?charset=utf8mb4"
    # Banco isolado do Financeiro. Vazio = deriva de DATABASE_URL (vps_host→financeiro).
    finance_database_url: str = ""
    # Segredo próprio das sessões/MFA do Financeiro. Vazio = deriva de SECRET_KEY.
    finance_secret_key: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    esxi_host: str = "192.168.0.125"
    esxi_user: str = "root"
    esxi_password: str = ""
    esxi_port: int = 443
    esxi_disable_ssl_verify: bool = False
    esxi_ssl_ca_file: str = ""
    esxi_ssl_pin_sha256: str = ""
    esxi_template_name: str = "VPS MODELO"
    esxi_datastore: str = "datastore1"
    esxi_network: str = "VM Network"

    ip_pool_start: str = "192.168.0.200"
    ip_pool_end: str = "192.168.0.250"
    ip_subnet_mask: str = "255.255.255.0"
    ip_gateway: str = "192.168.0.1"
    ip_dns_primary: str = "8.8.8.8"
    ip_dns_secondary: str = "8.8.4.4"

    guest_admin_user: str = "Administrator"
    guest_admin_password: str = ""
    guest_admin_password_sv2012: str = ""
    guest_admin_password_sv2016: str = ""
    guest_admin_password_sv2019: str = ""

    abacatepay_api_key: str = ""
    abacatepay_webhook_secret: str = ""
    abacatepay_base_url: str = "https://api.abacatepay.com/v2"
    abacatepay_enabled: bool = False

    skip_payment_for_testing: bool = False
    frontend_url: str = ""
    api_public_url: str = ""
    console_ws_ticket_seconds: int = 60
    auth_login_ip_max: int = 20
    auth_login_ip_window_seconds: int = 600
    auth_login_phone_fail_max: int = 8
    auth_login_phone_window_seconds: int = 900
    auth_register_ip_max: int = 5
    auth_register_ip_window_seconds: int = 3600
    auth_mfa_ip_max: int = 10
    auth_mfa_ticket_seconds: int = 120
    admin_mfa_required: bool = False
    auth_access_minutes: int = 15
    auth_refresh_hours: int = 12
    webauthn_rp_id: str = ""
    webauthn_rp_name: str = "CyberHost"
    webauthn_origin: str = ""

    # Confirmação de telefone via WhatsApp Cloud API (templates AUTHENTICATION).
    whatsapp_enabled: bool = False
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_template_name: str = "verification_code"
    whatsapp_template_language: str = "pt_BR"
    whatsapp_template_button: bool = True
    whatsapp_graph_version: str = "v22.0"
    whatsapp_otp_ttl_seconds: int = 600
    whatsapp_resend_seconds: int = 60
    whatsapp_send_ip_max: int = 10
    whatsapp_send_ip_window_seconds: int = 3600
    whatsapp_send_phone_max: int = 5
    whatsapp_send_phone_window_seconds: int = 3600
    whatsapp_verify_phone_max: int = 8
    whatsapp_verify_phone_window_seconds: int = 900

    email_otp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "CyberHost"
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    email_otp_ttl_seconds: int = 600
    email_otp_resend_seconds: int = 60
    email_send_ip_max: int = 10
    email_send_ip_window_seconds: int = 3600
    email_send_max: int = 5
    email_send_window_seconds: int = 3600
    email_verify_max: int = 8
    email_verify_window_seconds: int = 900
    billing_reminder_enabled: bool = True

    admin_phone: str = "11999999999"
    admin_password: str = ""

    cloud_files_path: str = "./data/cloud_files"
    finance_receipts_path: str = "./data/finance_receipts"
    finance_receipt_max_bytes: int = 8 * 1024 * 1024
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:cyberhost@ruts.dev"
    finance_timezone: str = "America/Sao_Paulo"
    finance_event_lead_minutes: int = 15
    cloud_files_quota_bytes: int = 5 * 1024 * 1024 * 1024
    # Espaço CyberCloud incluído em toda conta nova (GB).
    cloud_files_account_base_quota_gb: float = 20.0
    # Pacotes extras: "GB:preco_centavos" separados por vírgula (ex.: 50:990,100:1790).
    cloud_storage_packages: str = "50:990,100:1790,250:3990"
    # Limite por arquivo — prioridade: GB > MB > BYTES (veja _resolve_max_upload_bytes).
    cloud_files_max_upload_gb: float | None = None
    cloud_files_max_upload_mb: float = 200.0
    cloud_files_max_upload_bytes: int | None = None
    cloud_files_storage_backend: str = "local"
    # Limite de banda agregado no backend (upload, Discord, download). 0 = ilimitado.
    cloud_files_bandwidth_limit_mbps: float = 0.0
    # Uploads incompletos simultâneos por usuário (staging + reserva de cota).
    cloud_files_max_concurrent_uploads: int = 5
    # Teto do POST HTTP (multipart). 0 = só o limite do Discord.
    # O hop público (nginx 1.18) usa client_max_body_size 1m; 768 KiB passa com folga.
    cloud_files_http_chunk_max_bytes: int = 768 * 1024

    discord_bot_token: str = ""
    # Limite de anexo por mensagem na API do Discord (padrão 10 MiB; boost do servidor pode ser maior).
    discord_attachment_limit_bytes: int = 10 * 1024 * 1024
    discord_bot_tokens: str = ""
    discord_storage_channel_id: str = ""
    discord_url_cache_seconds: int = 22 * 60 * 60
    discord_upload_interval_seconds: float = 3.0

    # Servidores de jogo (SAMP, MTA, Minecraft, FiveM)
    game_servers_enabled: bool = True
    game_servers_data_path: str = "./data/game_servers"
    game_host_public_ip: str = "127.0.0.1"
    # Proxy Manager — mapeamento de portas públicas para IPs locais das VPS
    port_proxy_api_url: str = ""
    port_proxy_api_token: str = ""
    port_proxy_tls_pin_sha256: str = ""
    port_proxy_tls_ca_file: str = ""
    port_proxy_tls_insecure: bool = False
    # IP público exibido aos clientes nas portas de conexão (fallback: GAME_HOST_PUBLIC_IP)
    vps_public_ip: str = ""
    game_port_range_start: int = 27000
    game_port_range_end: int = 27999
    game_host_max_servers: int = 50
    # Limites de arquivos no diretório do servidor de jogo (upload/edição no painel).
    game_files_max_edit_bytes: int = 2 * 1024 * 1024
    game_files_max_upload_bytes: int = 50 * 1024 * 1024
    game_files_quota_bytes: int = 10 * 1024 * 1024 * 1024
    # Explorador e shell do host Linux no painel admin (caminhos absolutos, vírgula).
    host_files_roots: str = "/opt/host,/var/www/ruts"
    host_files_max_edit_bytes: int = 2 * 1024 * 1024
    host_files_max_upload_bytes: int = 50 * 1024 * 1024
    host_shell_enabled: bool = True
    host_shell_cwd: str = "/opt/host"
    # Isolamento do processo de game (Linux). Usuário sem login + cgroup via systemd-run.
    game_process_isolate: bool = True
    game_process_user: str = "cyberhost-game"
    game_process_owner: str = "rts"
    game_process_cpu_quota_percent: int = 100
    game_process_tasks_max: int = 128
    # Binários reais no host Linux (vazio = modo stub para dev/teste)
    game_samp_binary: str = ""
    game_mta_binary: str = ""
    game_minecraft_java: str = ""
    game_minecraft_jar: str = ""
    game_fivem_binary: str = ""
    # Chave padrão Cfx.re (https://keymaster.fivem.net) — cliente pode trocar no server.cfg
    game_fivem_default_license_key: str = ""

    # Hospedagem de sites (porta alta só em 127.0.0.1 + nginx 80)
    web_hosting_enabled: bool = True
    web_sites_data_path: str = "./data/web_sites"
    web_port_range_start: int = 30000
    web_port_range_end: int = 30499
    web_nginx_snippet_dir: str = ""
    web_nginx_reload: bool = True
    web_ssl_enabled: bool = True
    web_ssl_email: str = ""
    web_acme_webroot: str = "/var/www/acme"
    web_certbot_binary: str = "/usr/bin/certbot"
    web_public_base_url: str = ""
    web_platform_subdomains_enabled: bool = True
    web_platform_base_domain: str = ""
    web_php_binary: str = ""
    web_files_max_edit_bytes: int = 2 * 1024 * 1024
    web_files_max_upload_bytes: int = 50 * 1024 * 1024
    web_process_isolate: bool = True
    web_process_user: str = "cyberhost-web"
    web_process_owner: str = "rts"
    web_process_tasks_max: int = 64

    @property
    def discord_bot_token_list(self) -> list[str]:
        tokens: list[str] = []
        if self.discord_bot_tokens.strip():
            for part in self.discord_bot_tokens.replace("\n", ",").split(","):
                token = part.strip()
                if token:
                    tokens.append(token)
        if not tokens and self.discord_bot_token.strip():
            tokens.append(self.discord_bot_token.strip())
        return tokens

    @property
    def cloud_files_chunk_size_bytes(self) -> int:
        """Menor entre anexo Discord (−1 KB) e teto HTTP do proxy público."""
        discord_chunk = max(1024, self.discord_attachment_limit_bytes - 1024)
        http_max = int(self.cloud_files_http_chunk_max_bytes or 0)
        if http_max > 0:
            return max(1024, min(discord_chunk, http_max))
        return discord_chunk

    @property
    def discord_storage_enabled(self) -> bool:
        return (
            self.cloud_files_storage_backend.strip().lower() == "discord"
            and bool(self.discord_bot_token_list)
            and bool(self.discord_storage_channel_id.strip())
        )

    @field_validator(
        "guest_admin_user",
        "guest_admin_password",
        "guest_admin_password_sv2012",
        "guest_admin_password_sv2016",
        "guest_admin_password_sv2019",
        mode="before",
    )
    @classmethod
    def _strip_guest_credentials(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _resolve_max_upload_bytes(self) -> Self:
        explicit = self.model_fields_set
        if (
            "cloud_files_max_upload_gb" in explicit
            and self.cloud_files_max_upload_gb is not None
            and self.cloud_files_max_upload_gb > 0
        ):
            self.cloud_files_max_upload_bytes = int(self.cloud_files_max_upload_gb * 1024**3)
        elif "cloud_files_max_upload_mb" in explicit:
            self.cloud_files_max_upload_bytes = int(self.cloud_files_max_upload_mb * 1024 * 1024)
        elif (
            "cloud_files_max_upload_bytes" in explicit
            and self.cloud_files_max_upload_bytes is not None
        ):
            pass
        elif self.cloud_files_max_upload_bytes is None:
            self.cloud_files_max_upload_bytes = int(self.cloud_files_max_upload_mb * 1024 * 1024)
        return self

    @model_validator(mode="after")
    def _reject_weak_production_secret(self) -> Self:
        if self.app_environment.strip().lower() not in {"production", "prod"}:
            return self
        secret = self.secret_key.strip()
        placeholders = {
            "",
            "dev-secret-change-in-production",
            "change-me-to-a-random-64-char-string",
        }
        if secret in placeholders or len(secret) < 32:
            raise ValueError(
                "SECRET_KEY insegura para produção; configure um segredo aleatório com pelo menos 32 caracteres"
            )
        return self

    @model_validator(mode="after")
    def _reject_reused_payment_secrets(self) -> Self:
        environment = self.app_environment.strip().lower()
        production = environment in {"production", "prod"}
        if production and self.skip_payment_for_testing:
            raise ValueError(
                "SKIP_PAYMENT_FOR_TESTING não pode ser habilitado em produção"
            )
        if production and (not self.abacatepay_enabled or not self.abacatepay_api_key.strip()):
            raise ValueError(
                "AbacatePay deve estar habilitada com ABACATEPAY_API_KEY em produção"
            )
        if not self.abacatepay_enabled:
            return self
        api_key = self.abacatepay_api_key.strip()
        webhook_secret = self.abacatepay_webhook_secret.strip()
        if not api_key:
            raise ValueError(
                "ABACATEPAY_API_KEY é obrigatória quando AbacatePay está habilitada"
            )
        if not webhook_secret:
            raise ValueError(
                "ABACATEPAY_WEBHOOK_SECRET é obrigatório quando AbacatePay está habilitada"
            )
        if api_key and webhook_secret and api_key == webhook_secret:
            raise ValueError(
                "ABACATEPAY_WEBHOOK_SECRET deve ser diferente de ABACATEPAY_API_KEY"
            )
        if webhook_secret and len(webhook_secret) < 32:
            raise ValueError(
                "ABACATEPAY_WEBHOOK_SECRET deve ter pelo menos 32 caracteres"
            )
        return self

    @model_validator(mode="after")
    def _require_esxi_tls(self) -> Self:
        environment = self.app_environment.strip().lower()
        production = environment in {"production", "prod"}
        if production and self.esxi_disable_ssl_verify:
            raise ValueError(
                "ESXI_DISABLE_SSL_VERIFY não pode ser habilitado em produção"
            )
        if self.esxi_disable_ssl_verify:
            return self
        pin = "".join(ch for ch in self.esxi_ssl_pin_sha256 if ch in "0123456789abcdefABCDEF")
        ca_file = self.esxi_ssl_ca_file.strip()
        if pin and len(pin) != 64:
            raise ValueError("ESXI_SSL_PIN_SHA256 deve ser SHA-256 (64 hex)")
        if production and not pin and not ca_file:
            raise ValueError(
                "Produção exige ESXI_SSL_PIN_SHA256 ou ESXI_SSL_CA_FILE"
            )
        return self

    @model_validator(mode="after")
    def _require_https_public_urls(self) -> Self:
        if self.app_environment.strip().lower() not in {"production", "prod"}:
            return self
        frontend = self.resolved_frontend_url
        api = self.resolved_api_public_url
        if not _is_https_url(frontend):
            raise ValueError("FRONTEND_URL deve usar HTTPS em produção")
        if not _is_https_url(api):
            raise ValueError("API_PUBLIC_URL deve usar HTTPS em produção")
        frontend_origin = _origin_from_url(frontend).lower()
        cors_origins = {origin.rstrip("/").lower() for origin in self.cors_origin_list}
        if frontend_origin not in cors_origins:
            raise ValueError(
                "CORS_ORIGINS deve incluir a origem HTTPS do FRONTEND_URL em produção"
            )
        public_hosts = {"ruts.dev", "www.ruts.dev"}
        for origin in self.cors_origin_list:
            parsed = urlparse(origin)
            host = (parsed.hostname or "").lower()
            if host in public_hosts and parsed.scheme.lower() != "https":
                raise ValueError(
                    "CORS_ORIGINS do host público deve usar HTTPS em produção"
                )
        return self

    @model_validator(mode="after")
    def _require_port_proxy_tls(self) -> Self:
        url = self.port_proxy_api_url.strip()
        production = self.app_environment.strip().lower() in {"production", "prod"}
        if production and self.port_proxy_tls_insecure:
            raise ValueError(
                "PORT_PROXY_TLS_INSECURE não pode ser habilitado em produção"
            )
        if not url:
            return self
        if production and not _is_https_url(url):
            raise ValueError("PORT_PROXY_API_URL deve usar HTTPS em produção")
        token = self.port_proxy_api_token.strip()
        if production and len(token) < 32:
            raise ValueError(
                "PORT_PROXY_API_TOKEN deve ter pelo menos 32 caracteres em produção"
            )
        pin = "".join(
            ch for ch in self.port_proxy_tls_pin_sha256 if ch in "0123456789abcdefABCDEF"
        )
        if pin and len(pin) != 64:
            raise ValueError("PORT_PROXY_TLS_PIN_SHA256 deve ser SHA-256 (64 hex)")
        ca_file = self.port_proxy_tls_ca_file.strip()
        if production and not self.port_proxy_tls_insecure and not pin and not ca_file:
            raise ValueError(
                "Produção exige PORT_PROXY_TLS_PIN_SHA256 ou PORT_PROXY_TLS_CA_FILE"
            )
        return self

    @model_validator(mode="after")
    def _require_whatsapp_credentials(self) -> Self:
        if not self.whatsapp_enabled:
            return self
        token = self.whatsapp_access_token.strip()
        phone_id = self.whatsapp_phone_number_id.strip()
        if not token or not phone_id:
            raise ValueError(
                "WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID são obrigatórios "
                "quando WHATSAPP_ENABLED=true"
            )
        return self

    @model_validator(mode="after")
    def _require_email_otp_smtp(self) -> Self:
        if not self.email_otp_enabled:
            return self
        if not self.smtp_host.strip() or not self.smtp_from.strip():
            raise ValueError(
                "SMTP_HOST e SMTP_FROM são obrigatórios quando EMAIL_OTP_ENABLED=true"
            )
        return self

    def guest_password_for_os(self, os_template: str) -> str:
        """Senha do template Windows; permite override por versão do SO."""
        overrides = {
            "sv2012": self.guest_admin_password_sv2012,
            "sv2016": self.guest_admin_password_sv2016,
            "sv2019": self.guest_admin_password_sv2019,
        }
        specific = overrides.get(os_template.strip().lower(), "").strip()
        return specific or self.guest_admin_password

    @property
    def vapid_private_pem(self) -> str:
        return self.vapid_private_key.replace("\\n", "\n").strip()

    @property
    def web_push_configured(self) -> bool:
        return bool(self.vapid_public_key.strip() and self.vapid_private_pem)

    @property
    def finance_push_configured(self) -> bool:
        return self.web_push_configured

    @property
    def resolved_finance_secret_key(self) -> str:
        explicit = (self.finance_secret_key or "").strip()
        if explicit:
            return explicit
        return f"{self.secret_key}:financeiro"

    @property
    def resolved_finance_database_url(self) -> str:
        explicit = (self.finance_database_url or "").strip()
        if explicit:
            return explicit
        url = self.database_url
        if "/vps_host" in url:
            return url.replace("/vps_host", "/financeiro", 1)
        if url.startswith("sqlite"):
            if url.endswith(".db"):
                return url[:-3] + "_financeiro.db"
            return "sqlite:///./financeiro.db"
        if url.rstrip("/").endswith("vps_host"):
            return url.rstrip("/")[:-8] + "financeiro"
        raise ValueError(
            "Defina FINANCE_DATABASE_URL (não foi possível derivar de DATABASE_URL)"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def host_file_root_list(self) -> list[str]:
        return [part.strip() for part in self.host_files_roots.split(",") if part.strip()]

    @property
    def resolved_frontend_url(self) -> str:
        if self.frontend_url.strip():
            return self.frontend_url.strip().rstrip("/")
        origins = self.cors_origin_list
        return origins[0].rstrip("/") if origins else "http://localhost:3000"

    @property
    def resolved_api_public_url(self) -> str:
        if self.api_public_url.strip():
            return self.api_public_url.strip().rstrip("/")
        return "http://localhost:8810"


def get_settings() -> Settings:
    """Recarrega o .env a cada chamada (alterações no .env exigem nova requisição, não cache)."""
    return Settings()
