"""
Guest Operations — troca de IP dentro do guest Windows.

No ESXi standalone (sem vCenter), a customização via CloneSpec.customization
não está disponível. Usamos Guest Operations API para executar PowerShell
dentro da VM após o boot.
"""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Callable

from pyVmomi import vim

from app.config import Settings
from app.console_io import safe_log_info, safe_print, sanitize_for_console
from app.esxi_tls import read_esxi_https
from app.services.vmware.client import ESXiClient

logger = logging.getLogger(__name__)

GUEST_LOG_PATH = r"C:\vps-host-guest.log"


def _guest_auth(
    settings: Settings,
    *,
    password: str | None = None,
    username: str | None = None,
) -> vim.NamePasswordAuthentication:
    return vim.NamePasswordAuthentication(
        username=username or settings.guest_admin_user,
        password=password or settings.guest_admin_password,
        interactiveSession=False,
    )


def _candidate_guest_users(settings: Settings) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for name in (settings.guest_admin_user, "Administrator", "Administrador"):
        key = name.lower()
        if key not in seen:
            seen.add(key)
            candidates.append(name)
    return candidates


def _escape_ps_single_quoted(value: str) -> str:
    return value.replace("'", "''")


def _powershell_args(script: str) -> str:
    """Passa script multilinha via -EncodedCommand (evita quebrar com ; no -Command)."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return f"-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {encoded}"


def _build_windows_ip_script(
    ip: str,
    subnet_mask: str,
    gateway: str,
    dns_primary: str,
    dns_secondary: str,
) -> str:
    """Configura IP estático via netsh (mais confiável no Windows Server clonado)."""
    return f"""
$log = '{GUEST_LOG_PATH}'
function Log($msg) {{ Add-Content -Path $log -Value "$(Get-Date -Format o) $msg" }}
Set-Content -Path $log -Value "$(Get-Date -Format o) Iniciando"
try {{
    $adapter = Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -First 1
    if (-not $adapter) {{ $adapter = Get-NetAdapter | Select-Object -First 1 }}
    if (-not $adapter) {{ throw 'Nenhum adaptador de rede encontrado' }}
    $name = $adapter.Name
    Log "Adaptador: $name"

    Set-NetIPInterface -InterfaceAlias $name -Dhcp Disabled -ErrorAction SilentlyContinue
    & netsh interface ip set address "name=$name" static {ip} {subnet_mask} {gateway}
    if ($LASTEXITCODE -ne 0) {{ throw "netsh set address falhou (exit $LASTEXITCODE)" }}
    Log 'IP e gateway aplicados via netsh'

    & netsh interface ip set dns "name=$name" static {dns_primary} primary
    & netsh interface ip add dns "name=$name" {dns_secondary} index=2
    Log 'DNS aplicado via netsh'
    Log 'Concluido: {ip}'
    exit 0
}} catch {{
    Log "ERRO: $($_.Exception.Message)"
    exit 1
}}
""".strip()


def _build_network_diag_script() -> str:
    return f"""
$log = '{GUEST_LOG_PATH}'
function Log($msg) {{ Add-Content -Path $log -Value "$(Get-Date -Format o) $msg" }}
Log '=== Diagnostico de rede ==='
Get-NetAdapter | ForEach-Object {{ Log "Adapter: $($_.Name) Status=$($_.Status) ifIndex=$($_.ifIndex)" }}
Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object {{ Log "IPv4: $($_.IPAddress)/$($_.PrefixLength) ifIndex=$($_.InterfaceIndex)" }}
Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | ForEach-Object {{ Log "Gateway: $($_.NextHop) ifIndex=$($_.InterfaceIndex)" }}
Get-DnsClientServerAddress -AddressFamily IPv4 | ForEach-Object {{ Log "DNS ifIndex=$($_.InterfaceIndex): $($_.ServerAddresses -join ',')" }}
exit 0
""".strip()


def _guest_login_error(
    settings: Settings,
    *,
    template_name: str | None = None,
    guest_user: str | None = None,
) -> str:
    tpl = template_name or settings.esxi_template_name
    user = guest_user or settings.guest_admin_user
    return (
        f"Não foi possível autenticar no Windows como '{user}'. "
        f"Verifique GUEST_ADMIN_PASSWORD no .env (senha do template '{tpl}'). "
        f"A senha nova do cliente só é aplicada no último passo do provisionamento."
    )


def _guest_username_candidates(settings: Settings, guest_host: str | None = None) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for name in _candidate_guest_users(settings):
        key = name.lower()
        if key not in seen:
            seen.add(key)
            candidates.append(name)
        if guest_host:
            qualified = f"{guest_host}\\{name}"
            qkey = qualified.lower()
            if qkey not in seen:
                seen.add(qkey)
                candidates.append(qualified)
    return candidates


def resolve_guest_user(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    settings: Settings,
    *,
    password: str | None = None,
    template_name: str | None = None,
    timeout: int = 420,
    on_tick: Callable[[int, int], None] | None = None,
) -> str:
    """
    Descobre o usuário local do template (Administrator vs Administrador)
    e aguarda o guest aceitar login após o boot.
    """
    effective = password or settings.guest_admin_password
    if not effective:
        raise ValueError("GUEST_ADMIN_PASSWORD não configurado no .env")

    tpl = template_name or settings.esxi_template_name
    auth_mgr = client.content.guestOperationsManager.authManager
    moid = vm._moId
    start = time.time()
    tools_error_logged = False

    while time.time() - start < timeout:
        fresh = client.find_vm_by_moid(moid)
        if fresh is not None:
            vm = fresh
        guest = vm.guest
        guest_host = (guest.hostName or "").strip() if guest else ""
        candidates = _guest_username_candidates(settings, guest_host or None)
        elapsed = int(time.time() - start)
        if on_tick is not None:
            on_tick(elapsed, timeout)

        if guest and guest.toolsStatus == vim.vm.GuestInfo.ToolsStatus.toolsNotRunning:
            if not tools_error_logged:
                logger.warning(
                    "VMware Tools inativo em %s durante autenticação guest (host=%s)",
                    vm.name,
                    guest_host or "—",
                )
                tools_error_logged = True

        for username in candidates:
            auth = _guest_auth(settings, password=effective, username=username)
            try:
                auth_mgr.ValidateCredentials(vm, auth)
            except vim.fault.InvalidGuestLogin:
                continue
            except vim.fault.GuestOperationsUnavailable:
                break
            if username.lower() != settings.guest_admin_user.lower():
                logger.info(
                    "Guest auth: usando '%s' no template %s (GUEST_ADMIN_USER=%s)",
                    username,
                    tpl,
                    settings.guest_admin_user,
                )
            else:
                logger.info("Credenciais guest OK para VM %s (user=%s)", vm.name, username)
            return username
        elapsed = int(time.time() - start)
        logger.info(
            "Aguardando autenticação guest em %s (%ss/%ss, user=%s)",
            vm.name,
            elapsed,
            timeout,
            settings.guest_admin_user,
        )
        time.sleep(10)

    guest = vm.guest
    if guest and guest.toolsStatus == vim.vm.GuestInfo.ToolsStatus.toolsNotRunning:
        raise ValueError(
            "O Windows iniciou, mas o painel ainda não consegue configurar a VPS "
            "automaticamente. Aguarde o desktop aparecer e tente de novo, ou fale com o suporte."
        )

    tried = ", ".join(_candidate_guest_users(settings))
    raise ValueError(
        f"Não foi possível autenticar no Windows ({tried}) no template '{tpl}'. "
        f"Cada template pode ter senha diferente — confira GUEST_ADMIN_PASSWORD "
        f"ou GUEST_ADMIN_PASSWORD_SV2012/SV2016/SV2019 no .env. "
        f"Se a VM parou na tela de login ou Ctrl+Alt+Del, complete o OOBE/sysprep "
        f"no template com unattend.xml antes de clonar. "
        f"A senha do cliente só é definida no último passo do provisionamento."
    )


def verify_guest_credentials(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    settings: Settings,
    *,
    password: str | None = None,
    template_name: str | None = None,
    guest_user: str | None = None,
) -> None:
    """Valida usuário/senha do Windows antes de executar scripts."""
    effective = password or settings.guest_admin_password
    if not effective:
        raise ValueError("GUEST_ADMIN_PASSWORD não configurado no .env")

    auth = _guest_auth(settings, password=effective, username=guest_user)
    try:
        client.content.guestOperationsManager.authManager.ValidateCredentials(vm, auth)
        logger.info("Credenciais guest OK para VM %s (user=%s)", vm.name, guest_user or settings.guest_admin_user)
    except vim.fault.InvalidGuestLogin as exc:
        raise ValueError(
            _guest_login_error(settings, template_name=template_name, guest_user=guest_user)
        ) from exc


def _read_guest_log(client: ESXiClient, vm: vim.VirtualMachine, auth) -> str | None:
    fm = client.content.guestOperationsManager.fileManager
    try:
        info = fm.InitiateFileTransferFromGuest(vm, auth, GUEST_LOG_PATH)
        url = info.url.replace("*", client.settings.esxi_host)
        data = read_esxi_https(url, client.settings)
        return data.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Não foi possível ler log do guest %s: %s", GUEST_LOG_PATH, exc)
        return None


def _run_powershell_script(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    settings: Settings,
    script: str,
    label: str,
    timeout: int = 120,
    *,
    password: str | None = None,
    template_name: str | None = None,
    guest_user: str | None = None,
    fallback_password: str | None = None,
) -> None:
    effective_user = guest_user or settings.guest_admin_user
    effective_password = password or settings.guest_admin_password
    auth = _guest_auth(settings, password=effective_password, username=effective_user)
    verify_guest_credentials(
        client,
        vm,
        settings,
        password=effective_password,
        template_name=template_name,
        guest_user=effective_user,
    )

    pm = client.content.guestOperationsManager.processManager
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath="C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
        arguments=_powershell_args(script),
    )

    logger.info("Executando %s na VM %s", label, vm.name)
    safe_print(f"Guest ops: {label} em {vm.name}...")

    try:
        pid = pm.StartProgramInGuest(vm, auth, spec)
    except vim.fault.InvalidGuestLogin as exc:
        raise ValueError(
            _guest_login_error(settings, template_name=template_name, guest_user=effective_user)
        ) from exc

    exit_code = _wait_guest_process(
        pm,
        client,
        vm,
        pid,
        timeout=timeout,
        settings=settings,
        guest_user=effective_user,
        password=effective_password,
        fallback_password=fallback_password,
    )
    guest_log, log_auth = _read_guest_log_with_passwords(
        client,
        vm,
        settings,
        effective_user,
        [fallback_password, effective_password],
    )

    if guest_log:
        safe_log = sanitize_for_console(guest_log)
        safe_log_info(logger, "Log guest (%s):\n%s", label, safe_log)
        safe_print(f"--- Log guest ({label}) ---\n{safe_log}\n--- fim log ---")

    if exit_code != 0:
        detail = guest_log or f"exit code {exit_code}"
        raise RuntimeError(f"{label} falhou: {detail}")


def _read_guest_log_with_passwords(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    settings: Settings,
    guest_user: str,
    passwords: list[str | None],
) -> tuple[str | None, vim.NamePasswordAuthentication | None]:
    seen: set[str] = set()
    for raw in passwords:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        auth = _guest_auth(settings, password=raw, username=guest_user)
        guest_log = _read_guest_log(client, vm, auth)
        if guest_log:
            return guest_log, auth
    return None, None


def _wait_guest_process(
    pm,
    client: ESXiClient,
    vm: vim.VirtualMachine,
    pid: int,
    timeout: int = 120,
    *,
    settings: Settings,
    guest_user: str,
    password: str,
    fallback_password: str | None = None,
) -> int:
    """
    Aguarda processo no guest. Reautentica se a sessão cair (comum ao mudar IP ou senha).
    """
    start = time.time()
    moid = vm._moId
    current_password = password
    auth = _guest_auth(settings, password=current_password, username=guest_user)
    auth_failures = 0
    used_fallback = False
    max_auth_retries = 20

    while time.time() - start < timeout:
        fresh = client.find_vm_by_moid(moid)
        if fresh is not None:
            vm = fresh

        try:
            procs = pm.ListProcessesInGuest(vm, auth, [pid])
            auth_failures = 0
        except vim.fault.InvalidGuestLogin:
            auth_failures += 1
            if auth_failures > max_auth_retries:
                raise ValueError(
                    "Sessão guest expirou ou credenciais foram rejeitadas durante o script."
                )

            if fallback_password and not used_fallback:
                current_password = fallback_password
                used_fallback = True
                logger.info("Reautenticando guest com senha atualizada (%s)", vm.name)
            else:
                logger.info(
                    "Reautenticando guest após desconexão temporária em %s (tentativa %s)",
                    vm.name,
                    auth_failures,
                )
                time.sleep(12)

            auth = _guest_auth(settings, password=current_password, username=guest_user)
            continue
        except vim.fault.GuestOperationsUnavailable:
            auth_failures += 1
            if auth_failures > max_auth_retries:
                raise ValueError("Guest operations indisponível durante o script.")
            time.sleep(12)
            continue

        if procs and procs[0].endTime is not None:
            return procs[0].exitCode or 0
        time.sleep(3)

    raise TimeoutError(f"Processo guest {pid} não terminou em {timeout}s")


def guest_network_debug(
    client: ESXiClient, vm: vim.VirtualMachine, settings: Settings
) -> dict:
    """Coleta diagnóstico de rede e credenciais do guest Windows."""
    guest = vm.guest
    result: dict = {
        "vm_name": vm.name,
        "power_state": str(vm.runtime.powerState),
        "tools_status": str(guest.toolsStatus) if guest else None,
        "tools_running": str(guest.toolsRunningStatus) if guest else None,
        "guest_ip_reported": guest.ipAddress if guest else None,
        "guest_hostname": guest.hostName if guest else None,
        "guest_admin_user": settings.guest_admin_user,
        "credentials_ok": False,
        "credential_error": None,
        "guest_log": None,
        "planned_ip_pool": {
            "gateway": settings.ip_gateway,
            "subnet_mask": settings.ip_subnet_mask,
            "dns_primary": settings.ip_dns_primary,
            "dns_secondary": settings.ip_dns_secondary,
        },
    }

    if not settings.guest_admin_password:
        result["credential_error"] = "GUEST_ADMIN_PASSWORD vazio no .env"
        return result

    try:
        guest_user = resolve_guest_user(client, vm, settings, timeout=60)
        result["credentials_ok"] = True
        result["guest_admin_user"] = guest_user
    except ValueError as exc:
        result["credential_error"] = str(exc)
        return result

    if guest and guest.toolsStatus != vim.vm.GuestInfo.ToolsStatus.toolsOk:
        result["credential_error"] = f"Agente do Windows: {guest.toolsStatus}"
        return result

    try:
        _run_powershell_script(
            client,
            vm,
            settings,
            _build_network_diag_script(),
            "diagnostico-rede",
            timeout=60,
            guest_user=guest_user,
        )
        result["guest_log"] = _read_guest_log(
            client, vm, _guest_auth(settings, username=guest_user)
        )
    except Exception as exc:
        result["credential_error"] = str(exc)
        result["guest_log"] = _read_guest_log(
            client, vm, _guest_auth(settings, username=guest_user)
        )

    return result


def set_windows_static_ip(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    settings: Settings,
    ip: str,
    *,
    password: str | None = None,
    template_name: str | None = None,
    guest_user: str | None = None,
) -> None:
    """Executa script no guest Windows para definir IP estático."""
    script = _build_windows_ip_script(
        ip=ip,
        subnet_mask=settings.ip_subnet_mask,
        gateway=settings.ip_gateway,
        dns_primary=settings.ip_dns_primary,
        dns_secondary=settings.ip_dns_secondary,
    )
    _run_powershell_script(
        client,
        vm,
        settings,
        script,
        f"configurar-ip-{ip}",
        password=password,
        template_name=template_name,
        guest_user=guest_user or settings.guest_admin_user,
    )


def _build_windows_password_script(username: str, new_password: str) -> str:
    """Compatível com Windows Server 2016/2019 (sem Set-LocalUser)."""
    user = _escape_ps_single_quoted(username)
    pwd = _escape_ps_single_quoted(new_password)
    return f"""
$log = '{GUEST_LOG_PATH}'
function Log($msg) {{ Add-Content -Path $log -Value "$(Get-Date -Format o) $msg" }}
Set-Content -Path $log -Value "$(Get-Date -Format o) Alterando senha"
try {{
    $account = [ADSI]"WinNT://./{user},user"
    $account.SetPassword('{pwd}')
    $account.SetInfo()
    Log 'Senha alterada para {user}'
    exit 0
}} catch {{
    Log "ERRO: $($_.Exception.Message)"
    exit 1
}}
""".strip()


def _build_extend_c_volume_script() -> str:
    """Estende a partição C: para usar todo o espaço não alocado do disco."""
    return f"""
$log = '{GUEST_LOG_PATH}'
function Log($msg) {{ Add-Content -Path $log -Value "$(Get-Date -Format o) $msg" }}
Set-Content -Path $log -Value "$(Get-Date -Format o) Estendendo volume C:"
try {{
    Update-HostStorageCache
    Start-Sleep -Seconds 3

    $part = Get-Partition -DriveLetter C -ErrorAction Stop
    Update-Disk -Number $part.DiskNumber
    Start-Sleep -Seconds 2

    $supported = Get-PartitionSupportedSize -DriveLetter C
    $targetSize = $supported.SizeMax
    if ($part.Size -ge ($targetSize - 1MB)) {{
        Log "C: ja ocupa todo o espaco ($([math]::Round($part.Size/1GB, 2)) GB)"
        exit 0
    }}

    Resize-Partition -DriveLetter C -Size $targetSize -ErrorAction Stop
    $newPart = Get-Partition -DriveLetter C
    Log "C: estendido para $([math]::Round($newPart.Size/1GB, 2)) GB"
    exit 0
}} catch {{
    Log "Resize-Partition falhou: $($_.Exception.Message). Tentando diskpart..."
    $script = @"
select volume C
extend
exit
"@
    $output = $script | diskpart 2>&1
    $output | ForEach-Object {{ Log "diskpart: $_" }}
    if ($LASTEXITCODE -ne 0) {{ throw "diskpart extend falhou (exit $LASTEXITCODE)" }}
    $newPart = Get-Partition -DriveLetter C
    Log "C: estendido via diskpart para $([math]::Round($newPart.Size/1GB, 2)) GB"
    exit 0
}}
""".strip()


def extend_windows_c_volume(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    settings: Settings,
    *,
    password: str | None = None,
    template_name: str | None = None,
    guest_user: str | None = None,
) -> None:
    """Expande a partição C: no Windows após aumento do disco virtual no ESXi."""
    script = _build_extend_c_volume_script()
    _run_powershell_script(
        client,
        vm,
        settings,
        script,
        "estender-volume-C",
        timeout=180,
        password=password,
        template_name=template_name,
        guest_user=guest_user or settings.guest_admin_user,
    )


def _build_windows_rearm_script() -> str:
    """
    Rearm de ativação Windows (Server 2012/2016/2019).
    Reseta contagem de dias de avaliação; reinicia para aplicar.
    """
    return f"""
$log = '{GUEST_LOG_PATH}'
function Log($msg) {{ Add-Content -Path $log -Value "$(Get-Date -Format o) $msg" }}
Set-Content -Path $log -Value "$(Get-Date -Format o) Iniciando rearm Windows"
try {{
    $slmgr = Join-Path $env:SystemRoot 'System32\\slmgr.vbs'
    if (-not (Test-Path -LiteralPath $slmgr)) {{
        throw "slmgr.vbs nao encontrado em $slmgr"
    }}
    Log 'Executando slmgr.vbs /rearm'
    $output = (& cscript.exe //B //Nologo $slmgr /rearm 2>&1 | Out-String).Trim()
    if ($output) {{ Log $output }}
    $combined = $output.ToLower()
    if ($combined -match 'exceeded|maximum|0xc004d302|nao e possivel rearmar') {{
        Log 'Rearm indisponivel (limite atingido) — provisionamento continua sem reinicio'
        exit 2
    }}
    if ($LASTEXITCODE -ne 0) {{
        throw "slmgr /rearm falhou (exit $LASTEXITCODE): $output"
    }}
    Log 'Rearm OK — reiniciando em 10s para aplicar contagem de dias'
    & shutdown.exe /r /t 10 /f /c "CyberHost: aplicando rearm Windows"
    exit 0
}} catch {{
    Log "ERRO: $($_.Exception.Message)"
    exit 1
}}
""".strip()


def rearm_windows_activation(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    settings: Settings,
    guest_user: str,
    *,
    password: str | None = None,
    template_name: str | None = None,
) -> bool:
    """
    Executa slmgr /rearm no guest Windows.
    Retorna True se agendou reinício (rearm aplicado).
    """
    script = _build_windows_rearm_script()
    effective_user = guest_user or settings.guest_admin_user
    effective_password = password or settings.guest_admin_password
    auth = _guest_auth(settings, password=effective_password, username=effective_user)
    verify_guest_credentials(
        client,
        vm,
        settings,
        password=effective_password,
        template_name=template_name,
        guest_user=effective_user,
    )

    pm = client.content.guestOperationsManager.processManager
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath="C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
        arguments=_powershell_args(script),
    )

    logger.info("Executando rearm Windows em %s", vm.name)
    safe_print(f"Guest ops: rearm Windows em {vm.name}...")

    try:
        pid = pm.StartProgramInGuest(vm, auth, spec)
    except vim.fault.InvalidGuestLogin as exc:
        raise ValueError(
            _guest_login_error(settings, template_name=template_name, guest_user=effective_user)
        ) from exc

    exit_code = _wait_guest_process(
        pm,
        client,
        vm,
        pid,
        timeout=120,
        settings=settings,
        guest_user=effective_user,
        password=effective_password,
    )
    guest_log, _ = _read_guest_log_with_passwords(
        client,
        vm,
        settings,
        effective_user,
        [effective_password],
    )
    if guest_log:
        safe_log = sanitize_for_console(guest_log)
        safe_log_info(logger, "Log guest (rearm):\n%s", safe_log)

    if exit_code == 2:
        logger.warning("Rearm indisponível em %s (limite do Windows)", vm.name)
        return False
    if exit_code != 0:
        detail = guest_log or f"exit code {exit_code}"
        raise RuntimeError(f"Rearm Windows falhou: {detail}")

    logger.info("Rearm Windows OK em %s — aguardando reinício", vm.name)
    return True


def set_windows_password(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    settings: Settings,
    username: str,
    new_password: str,
    *,
    current_password: str | None = None,
    template_name: str | None = None,
) -> None:
    """Altera senha de um usuário local Windows via Guest Operations."""
    script = _build_windows_password_script(username, new_password)
    _run_powershell_script(
        client,
        vm,
        settings,
        script,
        f"alterar-senha-{username}",
        password=current_password,
        template_name=template_name,
        guest_user=username,
        fallback_password=new_password,
        timeout=90,
    )
