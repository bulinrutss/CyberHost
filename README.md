# CyberHost

CyberHost é uma plataforma de hospedagem em produção: site comercial, painel do cliente, administração, cobrança e a automação que liga o pedido pago à infraestrutura. O cliente contrata no site; o sistema provisiona o recurso, cobra a renovação e entrega console, arquivos e domínio sem intervenção manual.

Este repositório é o código dessa plataforma. Credenciais, banco e máquinas ficam fora do Git.

## O que está aqui

| Parte | Onde | Papel |
| --- | --- | --- |
| Site e painéis | `frontend` | Vitrine, cadastro, pedidos, dashboard, admin e financeiro |
| API | `backend` | Autenticação, provisionamento, cobrança, arquivos e operação |
| Gateway Discord | `backend/app/services/discord_gateway.py` | Mantém os bots do armazenamento online |
| Deploy | `deploy` | Unidades systemd e configuração nginx da borda |
| Documentação | `docs` | Instalação, integração VMware e pagamentos |

## Produtos

**VPS Windows.** O cliente escolhe vCPU, memória e hostname. Depois do pagamento, a API clona um template no VMware ESXi (pyVmomi), ajusta recursos, aplica IP pela rede do guest e guarda a senha de administrador cifrada. No painel: ligar e desligar, console no navegador (WebMKS), arquivo RDP, upgrade, renovação e publicação de portas.

**Hospedagem de sites.** Cada site sobe num processo isolado, escutando só em localhost, com o nginx na frente. Há subdomínio da plataforma ou domínio próprio, HTTPS via Let's Encrypt, editor de arquivos e construtor de página. A cota, o ciclo de vida e a renovação seguem o mesmo fluxo de pedido dos outros produtos.

**CyberCloud.** Armazenamento incluso na conta, com pacotes extras. O upload é fatiado, a cota é reservada antes da transferência e há teto de banda. Os fragmentos ficam num backend de objetos operado por vários bots Discord, com fila para respeitar o limite da API.

**Servidores de jogo.** O backend provisiona processos de jogo, portas e arquivos num usuário de sistema sem login. A vitrine pública desse produto está desligada por configuração; VPS, sites e nuvem seguem ativos.

**Financeiro.** Módulo separado, com banco e segredo de sessão próprios. Cobre lançamentos, comprovantes e notificações push, com login e MFA independentes do painel de hospedagem.

## Conta, cobrança e operação

- Cadastro com confirmação por e-mail (SMTP) e, quando habilitado, por WhatsApp.
- Sessão em cookie, access token curto, refresh, limite de tentativas por IP e por telefone.
- TOTP para administradores, passkeys (WebAuthn) e step-up antes de ações sensíveis, como revelar a senha da VPS.
- Checkout e webhook com a Abacate Pay (PIX). O webhook exige assinatura; o modo de teste não desliga essa verificação.
- Cupons, lembretes de vencimento e suspensão por inadimplência.
- Painel administrativo: clientes, instâncias, sites, proxy nginx, suporte e métricas do host.
- Tickets de suporte no dashboard do cliente.

## Arquitetura

```text
Navegador
   │
   ▼
Next.js ── /api ──► FastAPI ──► MariaDB
                      │
                      ├── ESXi (clone, energia, console, guest)
                      ├── nginx + processos de site
                      ├── Discord (fragmentos do CyberCloud)
                      └── Abacate Pay, SMTP, WhatsApp, Web Push
```

Em produção, três serviços systemd sobem juntos: API, frontend e o gateway Discord. O nginx termina TLS, publica os sites dos clientes e encaminha o console.

## Stack

- **API:** Python, FastAPI, SQLAlchemy, Pydantic, PyJWT, pyVmomi
- **Interface:** Next.js 14, React 18, TypeScript, Tailwind CSS
- **Dados:** MariaDB (painel e financeiro em bases separadas)
- **Infra:** VMware ESXi, nginx, systemd, Let's Encrypt
- **Pagamento:** Abacate Pay

## Estrutura

```text
backend/          API, modelos, serviços e testes
frontend/         site, dashboard, admin e financeiro
deploy/nginx      borda HTTP
deploy/systemd    backend, frontend e gateway Discord
docs/             instalação, VMware e pagamento
```

Configuração sensível entra por ambiente. O modelo está em `backend/.env.example` e nos exemplos do frontend. O arquivo `.env` real não é versionado.

## Executar localmente

Requisitos: Python 3.11+, Node.js 18+ e um MariaDB acessível. Provisionar VPS de verdade exige um ESXi com template Windows e VMware Tools. Sem o hypervisor, a API e a interface sobem para desenvolvimento da conta, dos pedidos e do painel.

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

A interface fica em `http://localhost:3000`. O passo a passo de banco, ESXi e variáveis está em [docs/SETUP.md](docs/SETUP.md).

## Documentação

| Documento | Conteúdo |
| --- | --- |
| [docs/SETUP.md](docs/SETUP.md) | Instalação e configuração |
| [docs/VMWARE_INTEGRATION.md](docs/VMWARE_INTEGRATION.md) | APIs do ESXi usadas no provisionamento |
| [docs/ABACATEPAY.md](docs/ABACATEPAY.md) | Checkout e webhook |
