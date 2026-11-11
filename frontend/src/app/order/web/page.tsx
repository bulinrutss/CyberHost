"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PageShell } from "@/components/ui/PageShell";
import { api, formatPrice, getToken, type WebPreset } from "@/lib/api";

type WebQuote = {
  subtotal_cents: number;
  discount_cents: number;
  total_cents: number;
  coupon_code?: string | null;
};

export default function WebOrderPage() {
  const router = useRouter();
  const [presets, setPresets] = useState<WebPreset[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [siteSlug, setSiteSlug] = useState("");
  const [couponCode, setCouponCode] = useState("");
  const [quote, setQuote] = useState<WebQuote | null>(null);
  const [quoteError, setQuoteError] = useState("");
  const [quoting, setQuoting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.webPresets().then((list) => {
      setPresets(list);
      const popular = list.find((item) => item.is_popular) ?? list[0];
      if (popular) setSelectedId(popular.id);
    });
  }, [router]);

  useEffect(() => {
    if (!selectedId) return;
    setQuoting(true);
    const timer = setTimeout(() => {
      void api
        .webQuote({ preset_id: selectedId, coupon_code: couponCode.trim() || null })
        .then((result) => {
          setQuote(result);
          setQuoteError("");
        })
        .catch((e) => {
          setQuote(null);
          setQuoteError(e instanceof Error ? e.message : "Erro na cotação");
        })
        .finally(() => setQuoting(false));
    }, 200);
    return () => clearTimeout(timer);
  }, [selectedId, couponCode]);

  const selected = presets.find((item) => item.id === selectedId) ?? null;

  const submit = async () => {
    if (!selectedId) {
      setError("Selecione um plano");
      return;
    }
    if (!siteSlug.trim()) {
      setError("Informe o nome do site (ex.: minha-loja)");
      return;
    }
    if (quoteError) {
      setError(quoteError);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const order = await api.createWebOrder({
        preset_id: selectedId,
        site_slug: siteSlug.trim(),
        coupon_code: couponCode.trim() || null,
      });
      router.push(`/order/web/complete?order=${order.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao criar pedido");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageShell>
      <div className="max-w-3xl mx-auto">
        <div className="mb-8">
          <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
            ← Voltar ao site
          </Link>
          <h1 className="text-3xl font-bold mt-4">Contratar hospedagem de site</h1>
          <p className="text-[var(--text-secondary)] mt-2 leading-relaxed">
            Seu site fica <strong className="text-[var(--text-primary)]">online e público</strong> com um link
            personalizado assim que a contratação for concluída. Cada plano inclui bônus de espaço no CyberCloud.
            Se preferir, use seu próprio domínio depois — é fácil, em poucos cliques no painel.
          </p>
        </div>

        <div className="grid sm:grid-cols-3 gap-3 mb-8">
          {presets.map((preset) => {
            const active = preset.id === selectedId;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => setSelectedId(preset.id)}
                className={`glass-card p-5 text-left transition-colors ${
                  active ? "border-[var(--accent)] ring-1 ring-[var(--accent)]" : ""
                }`}
              >
                {preset.is_popular && (
                  <p className="text-xs font-semibold text-[var(--accent)] mb-1">Mais escolhido</p>
                )}
                <h2 className="font-bold text-lg">{preset.name}</h2>
                <p className="text-2xl font-extrabold mt-2">{formatPrice(preset.price_cents)}</p>
                <p className="text-xs text-muted mb-3">/mês</p>
                <ul className="text-sm text-[var(--text-secondary)] space-y-1">
                  <li>{preset.ram_mb} MB RAM</li>
                  <li>
                    {preset.disk_mb >= 1024 ? `${preset.disk_mb / 1024} GB` : `${preset.disk_mb} MB`} disco
                  </li>
                  <li>{preset.php_enabled ? "PHP" : "HTML/CSS/JS"}</li>
                  {(preset.cloud_bonus_gb ?? 0) > 0 && (
                    <li className="text-[var(--accent)]">+{preset.cloud_bonus_gb} GB CyberCloud</li>
                  )}
                </ul>
              </button>
            );
          })}
        </div>

        <label className="block mb-6">
          <span className="block text-sm font-semibold text-[var(--text-secondary)] mb-2 uppercase tracking-wide">
            Nome do seu site
          </span>
          <input
            type="text"
            value={siteSlug}
            onChange={(e) => setSiteSlug(e.target.value.toLowerCase())}
            placeholder="minha-loja"
            className="w-full px-4 py-3 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
            maxLength={63}
          />
          <p className="text-xs text-muted mt-1">
            Esse nome vira o seu link personalizado. Letras minúsculas, números e hífen. Domínio próprio você
            configura depois no painel.
          </p>
        </label>

        <label className="block mb-6">
          <span className="block text-sm font-semibold text-[var(--text-secondary)] mb-2 uppercase tracking-wide">
            Cupom de desconto <span className="normal-case font-normal">(opcional)</span>
          </span>
          <input
            type="text"
            value={couponCode}
            onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
            placeholder="Ex.: LANCAMENTO10"
            className="w-full px-4 py-3 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
            maxLength={40}
          />
        </label>

        {selected && (
          <div className="text-sm text-[var(--text-secondary)] mb-4">
            {quoting ? (
              <p>Calculando total...</p>
            ) : quoteError ? (
              <p className="text-red-400">{quoteError}</p>
            ) : quote ? (
              <>
                {quote.discount_cents > 0 ? (
                  <>
                    <p>
                      Subtotal: <span className="line-through">{formatPrice(quote.subtotal_cents)}</span>
                    </p>
                    <p className="text-[var(--success)]">
                      Desconto: {formatPrice(quote.discount_cents)}
                      {quote.coupon_code ? ` (${quote.coupon_code})` : ""}
                    </p>
                  </>
                ) : null}
                <p>
                  Total agora: <strong>{formatPrice(quote.total_cents)}</strong>
                </p>
              </>
            ) : (
              <p>
                Total agora: <strong>{formatPrice(selected.price_cents)}</strong>
              </p>
            )}
          </div>
        )}

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            type="button"
            onClick={() => void submit()}
            disabled={loading || !selectedId || quoting || !!quoteError}
            className="btn-primary flex-1"
          >
            {loading ? "Processando..." : "Contratar site"}
          </button>
          <Link href="/order" className="btn-ghost text-center">
            Preciso de VPS Windows
          </Link>
        </div>
      </div>
    </PageShell>
  );
}
