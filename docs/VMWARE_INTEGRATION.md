# Integração VMware ESXi 6.7.0 Update 3

Documentação completa das APIs e métodos de integração disponíveis para o host **192.168.0.125** com template **VPS MODELO**, datastore **datastore1** e rede **VM Network**.

## Ambiente detectado

| Recurso | Valor |
|---------|-------|
| ESXi | 6.7.0 Update 3 (Build 15160138) |
| Modo | Standalone (sem vCenter) |
| Template | VPS MODELO (Windows Server 2016+, 70 GB, desligado) |
| Datastore | datastore1 |
| Rede | VM Network |
| VMs existentes | 11 |

---

## 1. APIs disponíveis — visão geral

O VMware oferece **duas famílias de API** para gerenciar vSphere/ESXi:

| API | Protocolo | ESXi 6.7 Standalone | Usado neste projeto |
|-----|-----------|---------------------|---------------------|
| **vSphere Web Services (VIM)** | SOAP/XML | ✅ Completo | ✅ **Principal (pyVmomi)** |
| **vSphere Automation (REST)** | JSON/HTTPS | ⚠️ Limitado sem vCenter | ❌ Não usado |
| **ESXi Embedded Host Client** | Web UI | ✅ Manual | — |
| **SSH / vim-cmd** | CLI | ✅ Completo | 📄 Documentado como alternativa |
| **govc** | CLI (Go) | ✅ Completo | 📄 Documentado como alternativa |
| **PowerCLI** | PowerShell | ✅ Completo | 📄 Documentado como alternativa |
| **OVF Tool** | CLI | ✅ Deploy/export | 📄 Para migração |

### Por que pyVmomi (SOAP) foi escolhido?

No ESXi **standalone** (sem vCenter), a **vSphere Web Services API** é a interface mais completa e estável para:

- Clonar VMs (`VirtualMachine.Clone`)
- Reconfigurar CPU/RAM (`ReconfigVM_Task`)
- Ligar/desligar (`PowerOn`, `PowerOff`)
- Guest Operations (`GuestOperationsManager`) — troca de IP dentro do Windows

A REST API do vSphere Automation no ESXi 6.7 tem cobertura **reduzida** comparada ao vCenter. Endpoints como `POST /rest/vcenter/vm?action=clone` funcionam melhor com vCenter Server.

---

## 2. vSphere Web Services API (pyVmomi) — implementação atual

### Instalação

```bash
pip install pyvmomi==8.0.3.0.1
```

### Conexão

```python
from pyVim.connect import SmartConnect, Disconnect
import ssl

context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

si = SmartConnect(
    host="192.168.0.125",
    user="root",
    pwd="sua-senha",
    port=443,
    sslContext=context,
)
content = si.RetrieveContent()
```

**Arquivo no projeto:** `backend/app/services/vmware/client.py`

### Operações implementadas

#### 2.1 Listar VMs

```python
container = content.viewManager.CreateContainerView(
    content.rootFolder, [vim.VirtualMachine], True
)
for vm in container.view:
    print(vm.name, vm.summary.runtime.powerState)
```

**API:** `ContainerView` + `vim.VirtualMachine`

#### 2.2 Clonar VM (Full Clone)

```python
relospec = vim.vm.RelocateSpec()
relospec.datastore = datastore  # datastore1

clonespec = vim.vm.CloneSpec()
clonespec.location = relospec
clonespec.powerOn = False
clonespec.template = False

task = template_vm.Clone(folder=dest_folder, name="VPS-NOVO", spec=clonespec)
```

**API:** `vim.VirtualMachine.Clone()`  
**Requisito:** Template deve estar **desligado**  
**Arquivo:** `backend/app/services/vmware/clone.py`

| Tipo de clone | API | ESXi 6.7 | Notas |
|---------------|-----|----------|-------|
| Full Clone | `Clone()` | ✅ | Usado no projeto |
| Linked Clone | `Clone()` + snapshot | ✅ | Economiza disco |
| Instant Clone | `InstantClone()` | ✅ 6.7+ | Mais rápido, requer script guest |

#### 2.3 Reconfigurar vCPU e RAM

```python
spec = vim.vm.ConfigSpec()
spec.numCPUs = 4
spec.memoryMB = 8192
task = vm.ReconfigVM_Task(spec=spec)
```

**API:** `vim.VirtualMachine.ReconfigVM_Task()`  
**Arquivo:** `backend/app/services/vmware/configure.py`

#### 2.4 Power Management

| Ação | API |
|------|-----|
| Ligar | `vm.PowerOn()` |
| Desligar | `vm.PowerOff()` |
| Suspend | `vm.Suspend()` |
| Reset | `vm.ResetVM_Task()` |
| Shutdown guest | `vm.ShutdownGuest()` |

#### 2.5 Guest Operations — troca de IP (Windows)

No ESXi **sem vCenter**, a customização via `CloneSpec.customization` (CustomizationSpec) **não funciona** para Windows. A solução é executar script dentro do guest após o boot.

**Requisitos:**
- VMware Tools instalado e rodando no template
- Credenciais de administrador do Windows (`GUEST_ADMIN_USER` / `GUEST_ADMIN_PASSWORD`)
- VM ligada e Tools em estado `toolsOk`

```python
auth = vim.NamePasswordAuthentication(
    username="Administrator",
    password="senha",
    interactiveSession=False,
)

spec = vim.vm.guest.ProcessManager.ProgramSpec(
    programPath="C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    arguments="-Command \"New-NetIPAddress ...\"",
)

pid = content.guestOperationsManager.processManager.StartProgramInGuest(vm, auth, spec)
```

**API:** `vim.vm.guest.GuestOperationsManager`  
**Arquivo:** `backend/app/services/vmware/guest_ops.py`

**Script executado:** configura IP estático, gateway e DNS via `New-NetIPAddress` e `Set-DnsClientServerAddress`.

#### 2.6 Outras APIs úteis (não implementadas ainda)

| API | Uso |
|-----|-----|
| `CreateSnapshot_Task` | Snapshot antes de updates |
| `RevertToSnapshot_Task` | Rollback |
| `Destroy_Task` | Remover VM |
| `RelocateVM_Task` | Mover para outro datastore |
| `RelocateVM_Task` + `VirtualDisk` | Expandir disco |
| `GuestOperationsManager.fileManager` | Upload/download de arquivos no guest |
| `GuestOperationsManager.authManager` | Validar credenciais guest |

---

## 3. vSphere Automation REST API

Base URL no ESXi: `https://192.168.0.125/rest/`

### Autenticação

```bash
# Criar sessão
curl -k -X POST https://192.168.0.125/rest/com/vmware/cis/session \
  -u root:senha

# Resposta: {"value": "<session-token>"}
# Usar header: vmware-api-session-id: <token>
```

### Endpoints úteis no ESXi 6.7

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/rest/com/vmware/cis/session` | Login |
| GET | `/rest/vcenter/vm` | Listar VMs |
| GET | `/rest/vcenter/vm/{vm}` | Detalhes da VM |
| POST | `/rest/vcenter/vm/{vm}/power/start` | Ligar VM |
| POST | `/rest/vcenter/vm/{vm}/power/stop` | Desligar VM |
| GET | `/rest/vcenter/host` | Info do host |
| GET | `/rest/vcenter/datastore` | Datastores |
| GET | `/rest/vcenter/network` | Redes |

### Clone via REST (limitado no ESXi standalone)

```bash
POST /rest/vcenter/vm?action=clone
{
  "spec": {
    "name": "VPS-NOVO",
    "source": "vm-XX",
    "placement": { "datastore": "datastore-YY" }
  }
}
```

⚠️ No ESXi standalone, clone via REST pode falhar ou ter funcionalidades reduzidas. **Recomendamos pyVmomi** para clone.

---

## 4. SSH + vim-cmd (alternativa CLI)

Habilite SSH no ESXi: **Host → Actions → Services → Enable SSH**

### Comandos essenciais

```bash
# Listar VMs
vim-cmd vmsvc/getallvms

# Info da VM (VMID = primeira coluna)
vim-cmd vmsvc/get.summary <VMID>

# Ligar / desligar
vim-cmd vmsvc/power.on <VMID>
vim-cmd vmsvc/power.off <VMID>

# Clonar (via arquivo VMX — método manual)
# 1. Desligar template
# 2. Copiar pasta da VM no datastore
# 3. Registrar nova VM:
vim-cmd solo/registervm /vmfs/volumes/datastore1/VPS-NOVO/VPS-NOVO.vmx "VPS-NOVO"

# Reconfigurar CPU (via vim-cmd é limitado — preferir API)
```

### Instant Clone via CLI (ESXi 6.7+)

```bash
# Requer VM source ligada com Tools
vim-cmd vmsvc/instantclone <source-vmid> <new-name> <new-ds-path>
```

---

## 5. govc (CLI Go — alternativa recomendada para scripts)

```bash
# Instalar: https://github.com/vmware/govmomi/releases
export GOVC_URL=https://root:senha@192.168.0.125/sdk
export GOVC_INSECURE=true

govc ls /ha-datacenter/vm/
govc vm.clone -vm="VPS MODELO" -on=false VPS-NOVO
govc vm.change -vm=VPS-NOVO -c 4 -m 8192
govc vm.power -on VPS-NOVO
```

---

## 6. PowerCLI (PowerShell)

```powershell
Connect-VIServer -Server 192.168.0.125 -User root -Password senha

Get-VM
New-VM -Name "VPS-NOVO" -VM "VPS MODELO" -Datastore datastore1
Set-VM -VM "VPS-NOVO" -NumCpu 4 -MemoryGB 8 -Confirm:$false
Start-VM -VM "VPS-NOVO"

# Executar script no guest (requer Tools)
Invoke-VMScript -VM "VPS-NOVO" -ScriptText { ... } -GuestUser Administrator -GuestPassword senha
```

---

## 7. Customização de Guest OS — comparativo

| Método | vCenter | ESXi Standalone | Windows | Implementado |
|--------|---------|-----------------|---------|--------------|
| CustomizationSpec no Clone | ✅ | ❌ | ✅ | ❌ |
| Guest Operations (script) | ✅ | ✅ | ✅ | ✅ |
| Sysprep manual no template | ✅ | ✅ | ✅ | Recomendado* |
| Cloud-init | ✅ | ✅ | Linux | N/A |
| DHCP no pool | ✅ | ✅ | ✅ | Alternativa |

\* **Recomendação para o template VPS MODELO:** Prepare o template com Sysprep (`C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown`) para que cada clone tenha SID único. O IP ainda será configurado via Guest Operations após o boot.

---

## 8. Fluxo de provisionamento deste projeto

```
Cliente cria pedido (vCPU, RAM, hostname)
        ↓
[Modo teste] Pula pagamento → status PAID
        ↓
Background task inicia provisionamento
        ↓
1. Aloca IP do pool (192.168.0.200–250)
2. Clone VPS MODELO → VPS-{HOSTNAME}
3. ReconfigVM (vCPU, RAM)
4. PowerOn
5. Aguarda VMware Tools
6. Guest Operations: PowerShell configura IP estático
        ↓
Status: RUNNING — cliente vê IP no dashboard
```

**Arquivo orquestrador:** `backend/app/services/vmware/provisioner.py`

---

## 9. Permissões necessárias no ESXi

O usuário `root` tem todas as permissões. Para usuário dedicado, crie role com:

- `VirtualMachine.Inventory.Create`
- `VirtualMachine.Config.AddNewDisk`
- `VirtualMachine.Config.CPUCount`
- `VirtualMachine.Config.Memory`
- `VirtualMachine.Interact.PowerOn`
- `VirtualMachine.Interact.PowerOff`
- `VirtualMachine.Provisioning.Clone`
- `VirtualMachine.GuestOperations.Execute`
- `Datastore.Browse`
- `Datastore.AllocateSpace`

---

## 10. Troubleshooting

| Problema | Causa | Solução |
|----------|-------|---------|
| SSL certificate verify failed | Certificado autoassinado | `ESXI_DISABLE_SSL_VERIFY=true` |
| Template not found | Nome exato diferente | Verificar com `GET /api/vmware/vms` |
| Clone falha | Template ligado | Desligar VPS MODELO |
| Guest Operations falha | Tools não instalado | Instalar VMware Tools no template |
| IP não aplicado | Senha guest errada | Configurar `GUEST_ADMIN_PASSWORD` |
| Pool de IPs esgotado | Muitas VPS | Ampliar `IP_POOL_START/END` |

---

## 11. Referências oficiais

- [vSphere Web Services API Reference](https://developer.broadcom.com/xapis/vsphere-web-services-api/latest/)
- [pyVmomi GitHub](https://github.com/vmware/pyvmomi)
- [pyVmomi Community Samples](https://github.com/vmware/pyvmomi-community-samples)
- [govmomi / govc](https://github.com/vmware/govmomi)
- [VMware PowerCLI](https://developer.broadcom.com/powercli)
- [KB 2003797 — Guest Customization](https://kb.vmware.com/s/article/2003797)
- [ESXi 6.7 Release Notes](https://docs.vmware.com/en/VMware-vSphere/6.7/rn/vsphere-esxi-67u3-release-notes.html)
