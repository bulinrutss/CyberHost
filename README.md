# VPS Host Panel

Painel web para automatizar venda e provisionamento de VPS Windows no **VMware ESXi 6.7**, clonando a partir do template **VPS MODELO**.

## Funcionalidades

- Cadastro e login de clientes
- Configurador de VPS (vCPU, RAM, hostname)
- Clone automático do template via **pyVmomi**
- Reconfiguração de recursos e troca de IP via **Guest Operations**
- Dashboard com status em tempo real
- Integração **Abacate Pay** preparada (modo teste ativo)

## Início rápido

```bash
# Backend
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # configure credenciais ESXi
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Acesse http://localhost:3000

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [docs/SETUP.md](docs/SETUP.md) | Instalação e configuração |
| [docs/VMWARE_INTEGRATION.md](docs/VMWARE_INTEGRATION.md) | **Todas as APIs VMware** (pyVmomi, REST, vim-cmd, govc, PowerCLI) |
| [docs/ABACATEPAY.md](docs/ABACATEPAY.md) | Pagamento (stub) |

## Stack

- **Backend:** FastAPI, SQLAlchemy, pyVmomi
- **Frontend:** Next.js 14, Tailwind CSS
- **VMware:** ESXi 6.7.0 U3 — vSphere Web Services API

## Seu ambiente

- Host: `192.168.0.125`
- Template: `VPS MODELO`
- Datastore: `datastore1`
- Rede: `VM Network`
