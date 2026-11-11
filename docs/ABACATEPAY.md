# Abacate Pay — Integração Preparada (Stub)

O sistema está **preparado** para integração com [Abacate Pay](https://abacatepay.com), mas o pagamento **não está implementado** para permitir testes sem cobrança.

## Estado atual

| Componente | Status |
|------------|--------|
| Interface `AbacatePayService` | ✅ Criada |
| Criação de checkout | 🔶 Retorna URL de teste |
| Webhook `/api/payments/webhook/abacatepay` | 🔶 Stub |
| Verificação de assinatura | ❌ TODO |
| Provisionamento após pagamento | ✅ Funciona via `SKIP_PAYMENT_FOR_TESTING` |

## Variáveis de ambiente

```env
ABACATEPAY_API_KEY=          # Chave da API (quando ativar)
ABACATEPAY_WEBHOOK_SECRET=   # Segredo para validar webhooks
ABACATEPAY_BASE_URL=https://api.abacatepay.com/v1
ABACATEPAY_ENABLED=false     # Manter false até implementar
SKIP_PAYMENT_FOR_TESTING=true
```

## Fluxo planejado (quando implementar)

```
1. Cliente cria pedido → status: pending_payment
2. Backend chama AbacatePayService.create_checkout()
3. Cliente é redirecionado para checkout_url da Abacate Pay
4. Após pagamento, Abacate Pay envia webhook para:
   POST /api/payments/webhook/abacatepay
5. Webhook valida assinatura → status: paid
6. Background task provisiona VPS no VMware
```

## Arquivos a modificar

- `backend/app/services/abacatepay.py` — implementar chamadas reais à API
- `backend/app/api/payments.py` — processar eventos do webhook
- `backend/app/api/orders.py` — remover skip automático quando `ABACATEPAY_ENABLED=true`
- `frontend/src/app/order/page.tsx` — redirecionar para checkout real

## Endpoint de teste manual

Para simular pagamento confirmado durante desenvolvimento:

```
POST /api/orders/{order_id}/confirm-payment
Authorization: Bearer <token>
```

## Webhook (estrutura esperada)

```json
{
  "type": "payment.confirmed",
  "metadata": {
    "order_id": "123"
  }
}
```

Implemente `verify_webhook_signature()` conforme documentação oficial da Abacate Pay quando obtiver acesso à API.
