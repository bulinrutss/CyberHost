# Checklist de remediação de segurança

Atualizado em: 2026-09-03

## Críticos

- [x] SEC-001 — Substituir `SECRET_KEY` padrão em produção, invalidar JWTs antigos e bloquear startup produtivo com segredo fraco.
- [x] SEC-002 — Rotacionar e remover credenciais reais de scripts e servidores; manter no histórico apenas valores revogados por decisão do proprietário.
- [x] SEC-003 — Separar e rotacionar `ABACATEPAY_API_KEY` e `ABACATEPAY_WEBHOOK_SECRET`; remover segredo de logs.
- [x] SEC-004 — Impedir cliente game de escrever `.cyberhost/state.json` e validar/isolar PIDs antes de encerrar processos.
- [x] SEC-005 — Autenticar webhooks sempre; nunca desabilitar secret/HMAC por modo de pagamento.

Observação SEC-002: o histórico remoto não será reescrito por decisão do proprietário. Os valores
históricos foram revogados e verificados. O host `192.168.0.130` foi retirado deste ambiente. As três
imagens Windows rejeitam a senha guest histórica; suas senhas atuais ainda devem ser cadastradas por
versão para restaurar operações automáticas dentro das VMs.

Observação SEC-008: o frontend permanece na linha Next 14.2 (14.2.35, último patch dessa
série). Advisories posteriores só saem em Next 15.5+/16 e exigem React 19; não foram misturados
nesta etapa. O otimizador de imagens continua desligado (`images.unoptimized`).

Observação SEC-009: a API SOAP e o WebSocket do console passam a validar o TLS do ESXi
com pin SHA-256. A transferência de arquivos guest foi coberta no SEC-010.

Observação SEC-011: o origin em :80 envia HSTS e redireciona `http://ruts.dev` para HTTPS,
exceto visitantes Cloudflare Flexible (`CF-Visitor`/`X-Forwarded-Proto: https`), ACME e
webhook. `FRONTEND_URL`/`API_PUBLIC_URL`/CORS públicos exigem HTTPS em produção. O console
usa WSS quando a página está em HTTPS. `http://ruts.dev` público ainda responde 521 no
Cloudflare (o pedido HTTP não chega ao origin); o redirect vale quando o origin é
alcançado. Habilitar Always Use HTTPS no painel Cloudflare fecha esse buraco na borda.

Observação SEC-012: o upload de fragmentos CyberCloud grava em disco em blocos com teto
igual ao tamanho do chunk; overflow vira 413 e o parcial `.part` é apagado. A montagem
local copia com `copyfileobj` e o download do CDN Discord também tem teto por fragmento.

Observação SEC-013: uploads incompletos reservam `size_bytes` na cota (com lock no
usuário). Há no máximo 5 simultâneos por conta e o fragmento não pode passar do
tamanho esperado pela reserva. Retomar um upload revalida a cota.

Observação SEC-014: edição no painel fica limitada a 2 MB; upload a 50 MB, com
streaming e teto. A pasta do servidor tem cota de 10 GB (`.cyberhost` não conta).
Overwrite só consome a diferença de tamanho.

Observação SEC-015: o processo de game no Linux roda como `cyberhost-game` via
`systemd-run` (cgroup v2): MemoryMax, CPUQuota, TasksMax, NoNewPrivileges,
PrivateTmp. O binário não pode estar na pasta do cliente. Windows/dev continua
com Popen local.

Observação SEC-016: o WebSocket do console deixa de aceitar JWT na query.
O painel pede um ticket de ~60s (uso único, hash no banco, compartilhado entre
workers) em `POST /console/ws-ticket` com Bearer e conecta com `?ticket=`.
`?token=` restante é rejeitado. O ticket WebMKS do ESXi em `/console/ticket`
não foi misturado nesta etapa.

Observação SEC-017: criar pedido reserva o cupom com `SELECT FOR UPDATE` e
incrementa `used_count` na hora; cotação não consome vaga. Redenção no
pagamento é idempotente e não estoura `max_uses`. Apagar pedido pendente
devolve a vaga.

Observação SEC-018: crédito e renovação CyberCloud só aplicam uma vez, com
lock de pedido e usuário. A segunda chamada não duplica GB nem vencimento.
Pedidos `cancelled` passaram a ser reconciliáveis no SEC-019.

Observação SEC-019: pedidos pendentes VPS/game/CyberCloud passam a
`cancelled` em vez de serem apagados. O `payment_external_id` permanece;
webhook e sync creditam um Pix pago depois. Hostname cancelado pode ser
reutilizado. O QR não é invalidado no provedor (a API não expõe cancelamento).

Observação SEC-020: `GET /api/payments/cloud-storage/complete` só redireciona
ao painel, sem consultar pedido, creditar ou revelar GB/status. O crédito
continua no webhook e nos POST autenticados de sync. O frontend não usa
`gb` da query; sincroniza com o dono logado.

Observação SEC-021: o bootstrap cria o admin só se o telefone ainda não
existir. Restart não regrava hash, não promove e não reativa conta já
cadastrada. `ADMIN_PASSWORD` no `.env` passa a ser ignorado depois da
primeira criação; rotacione pelo painel. Pode esvaziar a variável após
o bootstrap.

Observação SEC-022: login e registro passam a ter teto por IP/telefone no
banco (compartilhado entre workers), backoff 429 e alerta no journal ao
bloquear. Admin exige TOTP: primeiro acesso cadastra o autenticador;
os seguintes pedem o código. O nginx encaminha `CF-Connecting-IP` para
o backend. CAPTCHA de terceiro e fail2ban ficam fora desta etapa.

Observação SEC-023: apagar um arquivo CyberCloud some do painel na hora, mas
os IDs Discord vão para `cloud_discord_tombstones` até o DELETE na API
confirmar (404 conta como sucesso). O purge roda em loop com backoff e
não descarta tombstone sem confirmação. Arquivo só local não gera tombstone.

Observação SEC-024: senhas Windows em `vps_instances` ficam em envelope
Fernet (`enc:v1:`), derivado de `SECRET_KEY`. O startup alarga a coluna
para VARCHAR(512) e cifra texto puro. O detalhe da instância ainda devolve
a senha ao dono e registra auditoria sem o valor. Rotacionar `SECRET_KEY`
impede abrir envelopes antigos.

Observação SEC-025: o backend deixa de falar HTTP direto com o Proxy
Manager. Em produção a URL é HTTPS em `127.0.0.1:5443`, com Bearer e
pin/CA. Sem token o gateway responde 401; JSON inválido é recusado.
O Werkzeug em `192.168.0.127:5000` ainda é HTTP na LAN; o firewall
desse host fica no SEC-027.

Observação SEC-026: o painel lê no máximo 256 KiB do fim do
`.cyberhost/server.log`, em blocos de 8 KiB, e no máximo 500 linhas.
Se o arquivo passa de 8 MiB, há copytruncate com 3 gerações no start
e depois do tail.

Observação SEC-027: `.env` do backend e do frontend de produção ficam em
modo 600. uvicorn e Next escutam só `127.0.0.1` (8810/3000). o ufw nega
entrada exceto SSH, 80/443 e a faixa de game 27000–27999. O origin envia
HSTS, CSP, nosniff, `DENY`/`frame-ancestors` e Referrer-Policy. fail2ban
continua fora desta etapa. O Proxy Manager em `.127` ainda é HTTP na LAN.

Observação SEC-030: backups `.env.bak*` / `.env.example.bak*` foram
apagados na produção (não só chmod). `/opt/host/backend` e
`/opt/host/frontend` ficam em modo 700; `.env` live em 600. Os units
`cyberhost-backend`, `cyberhost-frontend` e `cyberhost-discord` usam
`UMask=0077` para arquivos futuros (ex.: novo `.env.bak`) nascerem 600.
A senha MariaDB do usuário da app foi rotacionada e alinhada em
`DATABASE_URL` e `FINANCE_DATABASE_URL` (valores não registrados aqui).

Observação SEC-028: a sessão vai no cookie `cyberhost_sid` (HttpOnly,
Secure em HTTPS, SameSite=Lax, **cookie de sessão** sem Max-Age — some ao
fechar o navegador; JWT com teto de 4 h se a aba ficar aberta). O nome
legado `cyberhost_session` é apagado no login/logout. O JSON de login não
devolve JWT. O painel só guarda a flag `ch_logged` e envia
`credentials: include`. `POST /api/auth/logout` apaga o cookie. Bearer
continua válido para scripts. Fechar só uma aba não encerra sessão
(limitação do navegador). “Continuar de onde parou” no Chrome pode
restaurar cookie de sessão após reboot. Toda resposta `/api/*` envia
`Cache-Control: private, no-store` + `CDN-Cache-Control: no-store` e
`Vary: Cookie` para a Cloudflare não reutilizar `/me` (ou listas) de um
usuário em outro — causa típica de “vi a conta de outra pessoa” entre
Observação SEC-028b: a sessão (cookie `cyberhost_sid`) fica amarrada ao
cookie de máquina `cyberhost_did`. Se a sessão for para outro PC sem o
mesmo `did`, a API responde 401 e exige login de novo. Bearer sem `did`
segue válido para scripts.

Observação SEC-029: a contenção de caminho do game (`_safe_path`, cwd,
binário) passa por `Path.is_relative_to` via `is_under_root`. Prefixo
textual (`/data/1` vs `/data/10`) deixa de ser aceito.

## Altos

- [x] SEC-006 — Tornar pagamentos fail-closed quando AbacatePay estiver desabilitada, sem chave ou mal configurada.
- [x] SEC-007 — Vincular webhook ao `payment_external_id` e validar status, valor, moeda, ambiente e metadata no provedor.
- [x] SEC-008 — Atualizar dependências vulneráveis do frontend e backend.
- [x] SEC-009 — Habilitar validação TLS/certificado ou pinning para o ESXi.
- [x] SEC-010 — Habilitar TLS verificado e timeout/leitura limitada na transferência de arquivos guest.
- [x] SEC-011 — Garantir HTTPS/WSS no origin, redirect HTTP e HSTS.
- [x] SEC-012 — Fazer streaming limitado dos chunks CyberCloud sem carregar o corpo inteiro em memória.
- [x] SEC-013 — Contabilizar/reservar uploads incompletos na cota e limitar concorrência/staging.
- [x] SEC-014 — Aplicar limite e cota aos uploads/edições de game server.
- [x] SEC-015 — Isolar código de game do cliente em container/UID e aplicar limites de recursos.
- [x] SEC-016 — Trocar JWT de 7 dias na query do console por ticket curto, único e não reutilizável.
- [x] SEC-017 — Reservar/redimir cupons atomicamente sob lock e respeitar `max_uses`.
- [x] SEC-018 — Tornar crédito/renovação CyberCloud idempotente e atômico sob concorrência.
- [x] SEC-030 — Apagar backups `.env.bak*` legíveis; dirs 700; `UMask=0077` nos serviços; rotacionar senha DB alinhada ao finance.

## Médios

- [x] SEC-019 — Trocar exclusão física de pedidos pendentes por cancelamento e reconciliar Pix pago posteriormente.
- [x] SEC-020 — Proteger retorno CyberCloud com proprietário autenticado ou state assinado; não mutar via GET público.
- [x] SEC-021 — Parar de restaurar a senha administrativa do `.env` em todo startup.
- [x] SEC-022 — Adicionar rate limit, backoff e alertas no login/registro; MFA para administradores.
- [x] SEC-023 — Excluir chunks/mensagens do Discord ao apagar arquivos e manter retry/tombstone.
- [x] SEC-024 — Criptografar senhas administrativas Windows armazenadas no banco.
- [x] SEC-025 — Autenticar e proteger com TLS a integração Port Proxy Manager.
- [x] SEC-026 — Ler tail de logs de game em blocos limitados e habilitar rotação.
- [x] SEC-027 — Restringir `.env` para modo 600, bind interno de 3000/8810, firewall e headers de segurança.
- [x] SEC-028 — Migrar JWT de `localStorage` para cookie HttpOnly/Secure/SameSite e reduzir duração.

## Baixos

- [x] SEC-029 — Substituir validação de caminho por prefixo textual por `Path.is_relative_to`.

## Critério para marcar

Marque `[x]` somente após implementação, testes, deploy aplicável e verificação em produção.
