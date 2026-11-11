"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { formatPrice } from "@/lib/api";
import { BusyLabel, InlineLoader } from "@/components/PageLoader";

export type Plan = {
  id: number;
  slug: string;
  name: string;
  description: string;
  min_vcpu: number;
  max_vcpu: number;
  min_ram_mb: number;
  max_ram_mb: number;
  network_mbps: number;
  default_disk_gb: number;
  max_disk_gb: number;
  price_per_vcpu_cents: number;
  price_per_gb_ram_cents: number;
  price_per_gb_disk_cents: number;
};

export type Preset = {
  id: number;
  plan_id: number;
  slug: string;
  name: string;
  vcpu: number;
  ram_mb: number;
  disk_gb: number;
  price_cents: number;
  cloud_bonus_gb?: number;
  is_popular: boolean;
  sort_order: number;
};

type ProductTab = "vps" | "semi_dedicated";

const TAB_LABELS: Record<ProductTab, string> = {
  vps: "VPS",
  semi_dedicated: "Semi-dedicado",
};

export type OsTemplate = {
  slug: string;
  label: string;
  template_name: string;
  is_recommended: boolean;
  recommended_min_vcpu: number;
  recommended_min_ram_mb: number;
  recommended_min_disk_gb: number;
  description: string;
};

export type QuoteResult = {
  total_cents: number;
  subtotal_cents: number;
  discount_cents: number;
  coupon_code?: string | null;
  warnings?: string[];
};

type Props = {
  plans: Plan[];
  presets: Preset[];
  osTemplates?: OsTemplate[];
  onQuote: (data: {
    plan_id: number;
    vcpu: number;
    ram_mb: number;
    disk_gb: number;
    preset_id: number | null;
    coupon_code?: string | null;
    os_template: string;
  }) => Promise<QuoteResult>;
  mode?: "simulator" | "order";
  hostname?: string;
  onHostnameChange?: (v: string) => void;
  onSubmit?: (config: {
    plan_id: number;
    preset_id: number | null;
    vcpu: number;
    ram_mb: number;
    disk_gb: number;
    coupon_code?: string | null;
    os_template: string;
  }) => void;
  submitLabel?: string;
  loading?: boolean;
  error?: string;
  paymentsRequired?: boolean;
};

export function VpsPlanConfigurator({
  plans,
  presets,
  osTemplates = [],
  onQuote,
  mode = "simulator",
  hostname = "",
  onHostnameChange,
  onSubmit,
  submitLabel = "Contratar agora",
  loading = false,
  error = "",
  paymentsRequired = false,
}: Props) {
  const [activeTab, setActiveTab] = useState<ProductTab>("vps");
  const [modeConfig, setModeConfig] = useState<"presets" | "custom">("presets");
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);
  const [vcpu, setVcpu] = useState(2);
  const [ramGb, setRamGb] = useState(2);
  const [diskGb, setDiskGb] = useState(30);
  const [couponCode, setCouponCode] = useState("");
  const [osTemplate, setOsTemplate] = useState("sv2016");
  const [quote, setQuote] = useState<QuoteResult | null>(null);
  const [quoteError, setQuoteError] = useState("");
  const [quoting, setQuoting] = useState(true);

  const plan = useMemo(
    () => plans.find((p) => p.slug === activeTab) ?? plans[0] ?? null,
    [plans, activeTab]
  );

  const tabPresets = useMemo(
    () => presets.filter((p) => p.plan_id === plan?.id).sort((a, b) => a.sort_order - b.sort_order),
    [presets, plan?.id]
  );

  const applyPreset = useCallback((preset: Preset) => {
    setSelectedPresetId(preset.id);
    setVcpu(preset.vcpu);
    setRamGb(preset.ram_mb / 1024);
    setDiskGb(preset.disk_gb);
  }, []);

  useEffect(() => {
    if (!plan) return;
    const first = tabPresets[0];
    if (first && modeConfig === "presets") {
      applyPreset(first);
    } else if (modeConfig === "custom") {
      setSelectedPresetId(null);
      setVcpu(plan.min_vcpu);
      setRamGb(Math.max(1, plan.min_ram_mb / 1024));
      setDiskGb(plan.default_disk_gb);
    }
  }, [plan?.id, activeTab, modeConfig, tabPresets, applyPreset, plan]);

  useEffect(() => {
    if (!plan) return;
    setQuoting(true);
    const timer = setTimeout(async () => {
      try {
        const result = await onQuote({
          plan_id: plan.id,
          vcpu,
          ram_mb: ramGb * 1024,
          disk_gb: diskGb,
          preset_id: modeConfig === "presets" ? selectedPresetId : null,
          coupon_code: couponCode.trim() || null,
          os_template: osTemplate,
        });
        setQuote(result);
        setQuoteError("");
      } catch (e) {
        setQuote(null);
        setQuoteError(e instanceof Error ? e.message : "Erro ao calcular");
      } finally {
        setQuoting(false);
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [plan, vcpu, ramGb, diskGb, selectedPresetId, modeConfig, couponCode, osTemplate, onQuote]);

  if (!plan) return null;

  const maxRamGb = plan.max_ram_mb / 1024;
  const minRamGb = Math.max(1, plan.min_ram_mb / 1024);

  return (
    <div className="space-y-6">
      <div className="flex gap-2 p-1.5 glass rounded-2xl">
        {(["vps", "semi_dedicated"] as ProductTab[]).map((tab) => {
          if (!plans.find((p) => p.slug === tab)) return null;
          const active = activeTab === tab;
          return (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-3 px-4 rounded-xl text-sm font-semibold transition-all ${
                active
                  ? "bg-[var(--accent)] text-white shadow-lg shadow-[var(--accent)]/20"
                  : "text-secondary hover:text-primary hover:bg-[var(--glass-bg)]"
              }`}
            >
              {TAB_LABELS[tab]}
            </button>
          );
        })}
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setModeConfig("presets")}
          className={`px-4 py-2 rounded-xl text-sm font-medium ${
            modeConfig === "presets" ? "btn-primary !py-2" : "btn-ghost !py-2"
          }`}
        >
          Planos prontos
        </button>
        <button
          type="button"
          onClick={() => setModeConfig("custom")}
          className={`px-4 py-2 rounded-xl text-sm font-medium ${
            modeConfig === "custom" ? "btn-primary !py-2" : "btn-ghost !py-2"
          }`}
        >
          Personalizado
        </button>
      </div>

      {modeConfig === "presets" && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {tabPresets.map((preset) => {
            const selected = selectedPresetId === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => applyPreset(preset)}
                className={`text-left rounded-2xl border p-5 transition-all ${
                  selected
                    ? "border-[var(--accent)] bg-[var(--accent)]/10 shadow-lg shadow-[var(--accent)]/10"
                    : "border-[var(--glass-border)] bg-[var(--glass-bg)] hover:border-[var(--accent)]/40"
                }`}
              >
                {preset.is_popular && (
                  <span className="text-[10px] uppercase tracking-wide font-bold text-[var(--accent)] mb-2 block">
                    Mais popular
                  </span>
                )}
                <h3 className="font-bold text-lg">{preset.name}</h3>
                <p className="text-2xl font-extrabold mt-2 text-[var(--accent)]">
                  {formatPrice(preset.price_cents)}
                  <span className="text-sm font-normal text-muted">/mês</span>
                </p>
                <ul className="text-sm text-secondary mt-4 space-y-1">
                  <li>{preset.vcpu} vCPU Xeon</li>
                  <li>{preset.ram_mb / 1024} GB RAM DDR4</li>
                  <li>{preset.disk_gb} GB NVMe SSD</li>
                  <li>{plan.network_mbps} Mb/s dedicado</li>
                  {(preset.cloud_bonus_gb ?? 0) > 0 && (
                    <li className="text-[var(--accent)]">
                      +{preset.cloud_bonus_gb} GB CyberCloud
                    </li>
                  )}
                </ul>
              </button>
            );
          })}
        </div>
      )}

      <div className="glass-card p-6 sm:p-8 space-y-6">
        {osTemplates.length > 0 && (
          <div>
            <label className="text-sm font-medium block mb-3">Sistema operacional</label>
            <div className="grid sm:grid-cols-2 gap-3">
              {osTemplates.map((os) => {
                const selected = osTemplate === os.slug;
                return (
                  <button
                    key={os.slug}
                    type="button"
                    onClick={() => setOsTemplate(os.slug)}
                    className={`text-left rounded-xl border p-4 transition-all ${
                      selected
                        ? "border-[var(--accent)] bg-[var(--accent)]/10"
                        : "border-[var(--glass-border)] hover:border-[var(--accent)]/40"
                    }`}
                  >
                    <p className="font-semibold text-sm">
                      {os.label}
                      {os.is_recommended && (
                        <span className="ml-1.5 text-[10px] uppercase text-[var(--accent)]">
                          (recomendado)
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-muted mt-1">{os.description}</p>
                    <p className="text-[10px] text-muted mt-2">
                      Mín. recomendado: {os.recommended_min_vcpu} vCPU ·{" "}
                      {os.recommended_min_ram_mb / 1024} GB RAM · {os.recommended_min_disk_gb} GB disco
                    </p>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {quote?.warnings && quote.warnings.length > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 space-y-1">
            <p className="text-sm font-medium text-amber-200">Configuração abaixo do recomendado</p>
            {quote.warnings.map((w) => (
              <p key={w} className="text-xs text-amber-100/90">
                {w}
              </p>
            ))}
          </div>
        )}

        <div className="grid sm:grid-cols-2 gap-4">
          <div className="glass rounded-xl p-4">
            <p className="text-xs text-muted uppercase tracking-wide mb-1">Rede</p>
            <p className="text-lg font-bold">{plan.network_mbps} Mb/s</p>
          </div>
          <div className="glass rounded-xl p-4">
            <p className="text-xs text-muted uppercase tracking-wide mb-1">Disco base</p>
            <p className="text-lg font-bold">{plan.default_disk_gb} GB</p>
            <p className="text-xs text-muted mt-1">Incluído no plano (template Windows)</p>
          </div>
        </div>

        {mode === "order" && onHostnameChange && (
          <div>
            <label className="text-sm font-medium block mb-2">Hostname</label>
            <input
              required
              minLength={3}
              maxLength={63}
              placeholder="meu-servidor"
              title="Use só letras sem acento, números e hífen. Sem espaços, ç ou ã."
              className="input-glass"
              value={hostname}
              onChange={(e) => onHostnameChange(e.target.value)}
            />
            <p className="text-xs text-muted mt-1.5">
              Só letras sem acento, números e hífen. Sem espaços ou caracteres em português (ç, ã, é).
            </p>
          </div>
        )}

        {(modeConfig === "custom" || modeConfig === "presets") && (
          <>
            {modeConfig === "custom" && (
              <>
                <div>
                  <div className="flex justify-between mb-2">
                    <label className="text-sm font-medium">vCPU</label>
                    <span className="text-[var(--accent)] font-bold">{vcpu}</span>
                  </div>
                  <input
                    type="range"
                    min={plan.min_vcpu}
                    max={plan.max_vcpu}
                    value={vcpu}
                    onChange={(e) => {
                      setSelectedPresetId(null);
                      setVcpu(Number(e.target.value));
                    }}
                    className="input-range"
                  />
                </div>
                <div>
                  <div className="flex justify-between mb-2">
                    <label className="text-sm font-medium">RAM</label>
                    <span className="text-[var(--accent)] font-bold">{ramGb} GB</span>
                  </div>
                  <input
                    type="range"
                    min={minRamGb}
                    max={maxRamGb}
                    step={1}
                    value={ramGb}
                    onChange={(e) => {
                      setSelectedPresetId(null);
                      setRamGb(Number(e.target.value));
                    }}
                    className="input-range"
                  />
                </div>
              </>
            )}

            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-medium">Disco NVMe</label>
                <span className="text-[var(--accent)] font-bold">{diskGb} GB</span>
              </div>
              <input
                type="range"
                min={plan.default_disk_gb}
                max={plan.max_disk_gb}
                step={1}
                value={diskGb}
                onChange={(e) => {
                  setDiskGb(Number(e.target.value));
                  if (modeConfig === "presets" && selectedPresetId) {
                    const p = tabPresets.find((x) => x.id === selectedPresetId);
                    if (p && Number(e.target.value) !== p.disk_gb) {
                      /* mantém preset para preço base + extra */
                    }
                  }
                }}
                className="input-range"
              />
              <p className="text-xs text-muted mt-1">
                Mín. {plan.default_disk_gb} GB incluídos. Acima disso: {formatPrice(plan.price_per_gb_disk_cents)}/GB/mês.
              </p>
            </div>

            <div>
              <label className="text-sm font-medium block mb-2">Cupom de desconto (opcional)</label>
              <input
                className="input-glass"
                placeholder="Ex.: LANCAMENTO10"
                value={couponCode}
                onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
              />
            </div>
          </>
        )}

        <div className="glass rounded-xl p-5 flex flex-wrap justify-between items-center gap-4">
          <div>
            {quoting ? (
              <InlineLoader label="Calculando preço…" />
            ) : (
              <>
                {quote && quote.discount_cents > 0 && (
                  <p className="text-sm text-muted line-through mb-1">
                    {formatPrice(quote.subtotal_cents)}/mês
                  </p>
                )}
                <p className="text-muted text-sm">Total estimado</p>
                <p className="text-3xl font-bold">
                  {quote !== null ? formatPrice(quote.total_cents) : "—"}
                  <span className="text-base font-normal text-muted">/mês</span>
                </p>
                {quote && quote.discount_cents > 0 && (
                  <p className="text-xs text-[var(--success)] mt-1">
                    Desconto de {formatPrice(quote.discount_cents)}
                    {quote.coupon_code ? ` (${quote.coupon_code})` : ""}
                  </p>
                )}
              </>
            )}
          </div>
          {mode === "order" && paymentsRequired && (
            <span className="text-xs font-medium text-[var(--success)] bg-[var(--success)]/10 px-3 py-1.5 rounded-full">
              PIX
            </span>
          )}
        </div>

        {(error || quoteError) && (
          <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-2">
            {error || quoteError}
          </p>
        )}

        {mode === "order" && onSubmit && (
          <button
            type="button"
            disabled={loading || quoting || quote === null}
            onClick={() =>
              onSubmit({
                plan_id: plan.id,
                preset_id: modeConfig === "presets" ? selectedPresetId : null,
                vcpu,
                ram_mb: ramGb * 1024,
                disk_gb: diskGb,
                coupon_code: couponCode.trim() || null,
                os_template: osTemplate,
              })
            }
            className="btn-primary w-full !py-3.5 text-base"
          >
            {loading ? <BusyLabel>Processando…</BusyLabel> : submitLabel}
          </button>
        )}
      </div>
    </div>
  );
}
