# Guia de Instalação e Configuração

## Pré-requisitos

- Python 3.11+
- Node.js 18+
- Acesso de rede ao ESXi `192.168.0.125` (porta 443)
- Template **VPS MODELO** desligado no ESXi
- VMware Tools instalado no template Windows
- Senha do administrador Windows do template

## 1. Configurar o ESXi

### Template VPS MODELO

1. A VM **VPS MODELO** deve estar **desligada** antes de clonar
2. Instale **VMware Tools** no Windows (se ainda não estiver)
3. Anote a senha do usuário `Administrator` (ou crie um usuário de serviço)
4. (Recomendado) Execute Sysprep antes de usar como template definitivo

### Pool de IPs

Configure no `.env` o range de IPs livres na sua rede local:

```env
IP_POOL_START=192.168.0.120
IP_POOL_END=192.168.0.250
IP_GATEWAY=192.168.0.1
IP_SUBNET_MASK=255.255.255.0
```

Certifique-se de que esses IPs não estão em uso por outras VMs ou dispositivos.

## 2. Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Edite .env com suas credenciais ESXi e guest Windows
```

### Variáveis obrigatórias

```env
ESXI_HOST=192.168.0.125
ESXI_USER=root
ESXI_PASSWORD=sua-senha-esxi
ESXI_TEMPLATE_NAME=VPS MODELO
ESXI_DATASTORE=datastore1
ESXI_NETWORK=VM Network

GUEST_ADMIN_USER=Administrator
GUEST_ADMIN_PASSWORD=senha-do-windows-template

SKIP_PAYMENT_FOR_TESTING=true
```

### Iniciar API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Documentação interativa: http://localhost:8000/docs

### Testar conexão VMware

Com um usuário logado, acesse:

```
GET http://localhost:8000/api/vmware/health
Authorization: Bearer <token>
```

## 3. Frontend

```bash
cd frontend
npm install
```

Crie `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

```bash
npm run dev
```

Acesse: http://localhost:3000

## 4. Fluxo de teste

1. Acesse http://localhost:3000
2. Crie uma conta em **Criar conta**
3. Vá em **Nova VPS**
4. Configure hostname, vCPU e RAM
5. Clique **Criar VPS agora**
6. Acompanhe em **Minhas VPS** — o status muda: `creating` → `configuring` → `running`
7. Quando `running`, o IP alocado aparece no dashboard

## 5. Estrutura do projeto

```
host/
├── backend/           # FastAPI + pyVmomi
│   └── app/
│       ├── api/       # Rotas REST
│       ├── services/
│       │   ├── vmware/  # Integração ESXi
│       │   └── abacatepay.py
│       └── models/
├── frontend/          # Next.js
├── docs/
│   ├── VMWARE_INTEGRATION.md
│   ├── ABACATEPAY.md
│   └── SETUP.md
└── README.md
```

## 6. Produção (notas)

- Troque `SECRET_KEY` por valor aleatório seguro
- Use PostgreSQL em vez de SQLite (`DATABASE_URL`)
- Configure HTTPS com reverse proxy (nginx/Caddy)
- Desative `SKIP_PAYMENT_FOR_TESTING` quando ativar Abacate Pay
- Restrinja acesso ao endpoint `/api/vmware/*` a administradores
