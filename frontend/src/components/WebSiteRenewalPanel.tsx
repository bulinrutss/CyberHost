"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, formatPrice, type WebSite } from "@/lib/api";
import { BusyLabel, InlineLoader } from "@/components/PageLoader";
import { InfoTip } from "@/components/ui/InfoTip";

type Billing = NonNullable<WebSite["billing"]>;

type Props = {
  site: WebSite;
  onUpdated: () => void;
  embedded?: boolean;
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function billingBadgeClass(state: Billing["billing_state"]) {
  if (state === "active") return "text-[var(--success)] bg-[var(--success)]/10 border-[var(--success)]/20";
  if (state === "grace") return "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/20";
  return "text-[var(--danger)] bg-[var(--danger)]/10 border-[var(--danger)]/20";
}

export function WebSiteRenewalPanel({ site, onUpdated, embedded = false }: Props) {
  const router = useRouter();
  const billing = site.billing;
  const [months, setMonths] = useState(1);
  const [quote, setQuote] = useState<{
    total_cents: number;
    monthly_cents: number;
    subtotal_cents: number;
    discount_cents: number;
    discount_percent: number;
    new_paid_until: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [quoting, setQuoting] = useState(true);
  const [error, setError] = useState("");
  const [paymentsRequired, setPaymentsRequired] = useState(false);

  useEffect(() => {
    api.paymentConfig().then((c) => setPaymentsRequired(c.payments_required));
  }, []);

  useEffect(() => {
    if (!billing || site.is_provisioning) return;
    setQuoting(true);
    const timer = setTimeout(async () => {
      try {
        const q = await api.webSiteRenewQuote(site.id, months);
        setQuote({
          total_cents: q.total_cents,
          monthly_cents: q.monthly_cents,
          subtotal_cents: q.subtotal_cents,
          discount_cents: q.discount_cents,
          discount_percent: q.discount_percent,
          new_paid_until: q.new_paid_until,
        });
        setError("");
      } catch (e) {
        setQuote(null);
        setError(e instanceof Error ? e.message : "Erro ao calcular renovação");
      } finally {
        setQuoting(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [site.id, months, billing, site.is_provisioning]);

  if (!billing || site.is_provisioning) return null;

  const submit = async () => {
    if (!quote) return;
    setLoading(true);
    setError("");
    try {
      const order = await api.webSiteCreateRenewal(site.id, months);
      router.push(`/order/web/complete?order=${order.id}&renew=1&site=${site.id}`);
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao renovar");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`glass-card p-6 sm:p-8 ${embedded ? "" : "mt-6"}`}>
      <div className="mb-6">
        <p className="text-sm text-[var(--accent)] uppercase tracking-wide mb-1">Mensalidade</p>
        <h2 className="text-xl font-bold inline-flex items-center gap-1.5">
          Renovação do site
          <InfoTip>
            O vencimento é até quando o site está pago. Pode renovar antes: os meses somam na data
            atual. Quanto mais meses, maior o desconto. Se atrasar, há alguns dias de carência; depois
            o site é desligado até pagar.
          </InfoTip>
        </h2>
      </div>

      <div
        className={`rounded-xl border px-4 py-3 mb-6 flex flex-wrap justify-between gap-3 items-center ${billingBadgeClass(billing.billing_state)}`}
      >
        <div>
          <p className="font-semibold">{billing.billing_label}</p>
          <p className="text-sm opacity-90">
            Vencimento: {formatDate(billing.paid_until)}
            {billing.billing_day > 0 && (
              <span className="text-xs block mt-0.5">Todo dia {billing.billing_day} de cada mês</span>
            )}
          </p>
        </div>
        {billing.monthly_cents != null && (
          <p className="text-lg font-bold">
            {formatPrice(billing.monthly_cents)}
            <span className="text-sm font-normal opacity-80">/mês</span>
          </p>
        )}
      </div>

      {billing.billing_state === "grace" && (
        <p className="text-sm text-[var(--warning)] mb-4">
          Sua mensalidade venceu. O site permanece no ar por até {billing.days_in_grace_left} dia(s) de
          carência antes de ser desligado.
        </p>
      )}

      {billing.billing_state === "suspended" && (
        <p className="text-sm text-[var(--danger)] mb-4">
          Site desligado por inadimplência. Renove para publicar novamente.
        </p>
      )}

      <div className="space-y-5">
        <div>
          <div className="flex justify-between mb-3">
            <label className="text-sm font-medium">Meses a renovar</label>
            <span className="text-[var(--accent)] font-bold">{months}</span>
          </div>
          <input
            type="range"
            min={1}
            max={12}
            step={1}
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
            className="input-range"
          />
          <p className="text-xs text-muted mt-1">
            Desconto progressivo até <strong className="text-secondary">20%</strong> em 12 meses.
          </p>
        </div>

        {quoting && <InlineLoader label="Calculando renovação…" />}

        {quote && !quoting && (
          <div className="glass rounded-xl p-4 space-y-3">
            <div className="flex flex-wrap justify-between items-start gap-4">
              <div>
                <p className="text-muted text-sm">Total da renovação</p>
                <p className="text-2xl font-bold">{formatPrice(quote.total_cents)}</p>
                {quote.discount_cents > 0 && (
                  <p className="text-xs text-[var(--success)] mt-1">
                    Economia de {formatPrice(quote.discount_cents)} ({quote.discount_percent}% de desconto)
                  </p>
                )}
                <p className="text-xs text-muted mt-1">
                  Novo vencimento: {formatDate(quote.new_paid_until)}
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-2">
            {error}
          </p>
        )}

        <button
          type="button"
          disabled={loading || quoting || !quote}
          onClick={submit}
          className="btn-primary w-full !py-3"
        >
          {loading ? (
            <BusyLabel>Processando…</BusyLabel>
          ) : paymentsRequired ? (
            "Pagar renovação"
          ) : (
            "Renovar agora"
          )}
        </button>
      </div>
    </div>
  );
}
