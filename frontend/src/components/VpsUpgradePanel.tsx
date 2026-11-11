"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, formatPrice, type VpsInstanceDetail } from "@/lib/api";
import { BusyLabel, InlineLoader, PageLoader } from "@/components/PageLoader";
import { InfoTip } from "@/components/ui/InfoTip";

type Plan = {
  id: number;
  slug: string;
  name: string;
  max_vcpu: number;
  max_ram_mb: number;
  max_disk_gb: number;
  min_ram_mb: number;
  min_vcpu: number;
  default_disk_gb: number;
  network_mbps: number;
  price_per_vcpu_cents: number;
  price_per_gb_ram_cents: number;
  price_per_gb_disk_cents: number;
};

type Preset = {
  id: number;
  plan_id: number;
  slug: string;
  name: string;
  vcpu: number;
  ram_mb: number;
  disk_gb: number;
  price_cents: number;
  is_popular: boolean;
  sort_order: number;
  cloud_bonus_gb?: number;
};

type QuoteInfo = {
  total_cents: number;
  monthly_delta_cents: number;
  current_monthly_cents: number;
  new_monthly_cents: number;
  days_remaining: number;
  period_days: number;
  prorated: boolean;
};

type PlanTab = "vps" | "semi_dedicated";
type UpgradeMode = "resources" | "plan";

type Props = {
  instance: VpsInstanceDetail;
  onUpdated: () => void;
  embedded?: boolean;
};

function formatDueDate(iso?: string | null) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function planChangeState(
  instance: VpsInstanceDetail,
  preset: Preset,
  plan: Plan,
  currentMonthly: number
): "current" | "upgrade" | "downgrade" | "cheaper" {
  const currentDisk = instance.disk_gb ?? 30;
  if (
    preset.vcpu < instance.vcpu ||
    preset.ram_mb < instance.ram_mb ||
    preset.disk_gb < currentDisk ||
    plan.network_mbps < instance.network_mbps
  ) {
    return "downgrade";
  }
  if (
    preset.vcpu === instance.vcpu &&
    preset.ram_mb === instance.ram_mb &&
    preset.disk_gb === currentDisk &&
    plan.network_mbps === instance.network_mbps
  ) {
    return "current";
  }
  if (preset.price_cents <= currentMonthly) return "cheaper";
  return "upgrade";
}

export function VpsUpgradePanel({ instance, onUpdated, embedded = false }: Props) {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [mode, setMode] = useState<UpgradeMode>("resources");
  const [planTab, setPlanTab] = useState<PlanTab>(
    instance.plan_slug === "semi_dedicated" ? "semi_dedicated" : "vps"
  );
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);
  const [vcpu, setVcpu] = useState(instance.vcpu);
  const [ramGb, setRamGb] = useState(instance.ram_mb / 1024);
  const [diskGb, setDiskGb] = useState(instance.disk_gb ?? 30);
  const [quote, setQuote] = useState<QuoteInfo | null>(null);
  const [catalogReady, setCatalogReady] = useState(false);
  const [quoting, setQuoting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [paymentsRequired, setPaymentsRequired] = useState(false);

  const currentDisk = instance.disk_gb ?? 30;
  const currentMonthly = instance.billing?.monthly_cents ?? 0;
  const dueLabel = formatDueDate(instance.billing?.paid_until);

  const currentPlan = useMemo(() => {
    const slug = instance.plan_slug || "vps";
    return plans.find((p) => p.slug === slug) ?? plans[0] ?? null;
  }, [plans, instance.plan_slug]);

  const tabPlan = useMemo(
    () => plans.find((p) => p.slug === planTab) ?? null,
    [plans, planTab]
  );

  const tabPresets = useMemo(
    () =>
      presets
        .filter((p) => p.plan_id === tabPlan?.id)
        .sort((a, b) => a.sort_order - b.sort_order),
    [presets, tabPlan?.id]
  );

  const selectedPreset = useMemo(
    () => presets.find((p) => p.id === selectedPresetId) ?? null,
    [presets, selectedPresetId]
  );

  const hasResourceChanges =
    vcpu > instance.vcpu || ramGb > instance.ram_mb / 1024 || diskGb > currentDisk;
  const hasPlanChange = Boolean(selectedPresetId);
  const hasChanges = mode === "plan" ? hasPlanChange : hasResourceChanges;

  useEffect(() => {
    Promise.all([api.plans(), api.presets(), api.paymentConfig()])
      .then(([planList, presetList, config]) => {
        setPlans(planList as Plan[]);
        setPresets(presetList as Preset[]);
        setPaymentsRequired(config.payments_required);
      })
      .finally(() => setCatalogReady(true));
  }, []);

  useEffect(() => {
    setVcpu(instance.vcpu);
    setRamGb(instance.ram_mb / 1024);
    setDiskGb(instance.disk_gb ?? 30);
  }, [instance.vcpu, instance.ram_mb, instance.disk_gb]);

  useEffect(() => {
    if (!hasChanges) {
      setQuote(null);
      setQuoting(false);
      return;
    }
    setQuoting(true);
    const timer = setTimeout(async () => {
      try {
        const payload =
          mode === "plan" && selectedPreset
            ? {
                target_vcpu: selectedPreset.vcpu,
                target_ram_mb: selectedPreset.ram_mb,
                target_disk_gb: selectedPreset.disk_gb,
                preset_id: selectedPreset.id,
              }
            : {
                target_vcpu: vcpu,
                target_ram_mb: ramGb * 1024,
                target_disk_gb: diskGb,
              };
        const result = await api.upgradeQuote(instance.id, payload);
        setQuote({
          total_cents: result.total_cents,
          monthly_delta_cents: result.monthly_delta_cents,
          current_monthly_cents: result.current_monthly_cents,
          new_monthly_cents: result.new_monthly_cents,
          days_remaining: result.days_remaining,
          period_days: result.period_days,
          prorated: result.prorated,
        });
        setError("");
      } catch (e) {
        setQuote(null);
        setError(e instanceof Error ? e.message : "Erro ao calcular upgrade");
      } finally {
        setQuoting(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [
    mode,
    hasChanges,
    instance.id,
    vcpu,
    ramGb,
    diskGb,
    selectedPreset,
  ]);

  const maxRamGb = useMemo(
    () => (currentPlan ? currentPlan.max_ram_mb / 1024 : 8),
    [currentPlan]
  );
  const maxDiskGb = currentPlan?.max_disk_gb ?? 500;

  const submit = async () => {
    if (!hasChanges || quote === null) return;
    setLoading(true);
    setError("");
    try {
      const payload =
        mode === "plan" && selectedPreset
          ? {
              target_vcpu: selectedPreset.vcpu,
              target_ram_mb: selectedPreset.ram_mb,
              target_disk_gb: selectedPreset.disk_gb,
              preset_id: selectedPreset.id,
            }
          : {
              target_vcpu: vcpu,
              target_ram_mb: ramGb * 1024,
              target_disk_gb: diskGb,
            };
      const order = await api.createUpgrade(instance.id, payload);
      router.push(`/order/complete?order=${order.id}&upgrade=1&instance=${instance.id}`);
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao solicitar upgrade");
    } finally {
      setLoading(false);
    }
  };

  if (instance.is_provisioning) return null;

  if (!catalogReady || !currentPlan) {
    return <PageLoader label="Carregando planos…" compact />;
  }

  return (
    <div className={`glass-card p-6 sm:p-8 ${embedded ? "" : "mt-6"}`}>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-[var(--accent)] uppercase tracking-wide mb-1">Recursos</p>
          <h2 className="text-xl font-bold inline-flex items-center gap-1.5">
            Upgrade do servidor
            <InfoTip>
              Aumente CPU, RAM ou disco, ou troque de plano. O valor de agora cobre a
              diferença até a renovação (todo o período já pago). Na próxima renovação o
              preço já é o novo. Não é possível reduzir recursos por aqui.
            </InfoTip>
          </h2>
          <p className="text-secondary text-sm mt-2 max-w-xl">
            Aumente recursos ou troque para um plano maior. O valor de agora cobre o extra
            até a renovação; a próxima cobrança já sai no preço novo.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => {
              setMode("resources");
              setSelectedPresetId(null);
              setError("");
              setQuote(null);
            }}
            className={`!py-2 text-sm ${mode === "resources" ? "btn-primary" : "btn-ghost"}`}
          >
            Ajustar recursos
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("plan");
              setVcpu(instance.vcpu);
              setRamGb(instance.ram_mb / 1024);
              setDiskGb(currentDisk);
              setError("");
              setQuote(null);
            }}
            className={`!py-2 text-sm ${mode === "plan" ? "btn-primary" : "btn-ghost"}`}
          >
            Trocar plano
          </button>
        </div>
      </div>

      {mode === "plan" ? (
        <div className="space-y-6">
          <div className="flex gap-2">
            {(["vps", "semi_dedicated"] as PlanTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => {
                  setPlanTab(tab);
                  setSelectedPresetId(null);
                  setQuote(null);
                  setError("");
                }}
                className={`!py-2 text-sm ${planTab === tab ? "btn-primary" : "btn-ghost"}`}
              >
                {tab === "vps" ? "VPS" : "Semi-dedicado"}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted">
            Só entram planos maiores que o atual. Não há downgrade.
            {tabPlan ? ` Rede ${tabPlan.network_mbps} Mb/s.` : ""}
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {tabPresets.map((preset) => {
              if (!tabPlan) return null;
              const state = planChangeState(instance, preset, tabPlan, currentMonthly);
              const selected = selectedPresetId === preset.id;
              const disabled = state !== "upgrade";
              const hint =
                state === "current"
                  ? "Plano atual"
                  : state === "downgrade"
                    ? "Menos recursos"
                    : state === "cheaper"
                      ? "Não aumenta a mensalidade"
                      : null;
              return (
                <button
                  key={preset.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    setSelectedPresetId(preset.id);
                    setError("");
                  }}
                  className={`text-left rounded-2xl border p-5 transition-all ${
                    selected
                      ? "border-[var(--accent)] bg-[var(--accent)]/10 shadow-lg shadow-[var(--accent)]/10"
                      : disabled
                        ? "border-[var(--glass-border)] bg-[var(--glass-bg)] opacity-50 cursor-not-allowed"
                        : "border-[var(--glass-border)] bg-[var(--glass-bg)] hover:border-[var(--accent)]/40"
                  }`}
                >
                  {preset.is_popular && state === "upgrade" && (
                    <span className="text-[10px] uppercase tracking-wide font-bold text-[var(--accent)] mb-2 block">
                      Mais popular
                    </span>
                  )}
                  {hint && (
                    <span className="text-[10px] uppercase tracking-wide font-bold text-muted mb-2 block">
                      {hint}
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
                    <li>{tabPlan.network_mbps} Mb/s dedicado</li>
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
        </div>
      ) : (
        <div className="space-y-6">
          <div>
            <div className="flex justify-between mb-3">
              <label className="text-sm font-medium">vCPU</label>
              <span className="text-[var(--accent)] font-bold">{vcpu}</span>
            </div>
            <input
              type="range"
              min={instance.vcpu}
              max={currentPlan.max_vcpu}
              value={vcpu}
              onChange={(e) => setVcpu(Number(e.target.value))}
              className="input-range"
            />
            <p className="text-xs text-muted mt-1">
              Atual: {instance.vcpu} — máx. {currentPlan.max_vcpu}
            </p>
          </div>

          <div>
            <div className="flex justify-between mb-3">
              <label className="text-sm font-medium">RAM</label>
              <span className="text-[var(--accent)] font-bold">{ramGb} GB</span>
            </div>
            <input
              type="range"
              min={instance.ram_mb / 1024}
              max={maxRamGb}
              step={1}
              value={ramGb}
              onChange={(e) => setRamGb(Number(e.target.value))}
              className="input-range"
            />
            <p className="text-xs text-muted mt-1">
              Atual: {instance.ram_mb / 1024} GB — máx. {maxRamGb} GB
            </p>
          </div>

          <div>
            <div className="flex justify-between mb-3">
              <label className="text-sm font-medium">Disco</label>
              <span className="text-[var(--accent)] font-bold">{diskGb} GB</span>
            </div>
            <input
              type="range"
              min={currentDisk}
              max={maxDiskGb}
              step={10}
              value={diskGb}
              onChange={(e) => setDiskGb(Number(e.target.value))}
              className="input-range"
            />
            <p className="text-xs text-muted mt-1">
              Atual: {currentDisk} GB — máx. {maxDiskGb} GB. O volume C: é expandido automaticamente
              após o pagamento.
            </p>
          </div>
        </div>
      )}

      {hasChanges && quoting && (
        <div className="glass rounded-xl p-4 mt-6">
          <InlineLoader label="Calculando upgrade…" />
        </div>
      )}

      {hasChanges && quote !== null && !quoting && (
        <div className="glass rounded-xl p-4 mt-6 space-y-3">
          <div className="flex justify-between items-start gap-4">
            <div>
              <p className="text-muted text-sm">
                {quote.prorated
                  ? `Pagar agora (proporcional${dueLabel ? ` até ${dueLabel}` : " até o vencimento"})`
                  : `Pagar agora${dueLabel ? ` · vencimento ${dueLabel}` : ""}`}
              </p>
              <p className="text-2xl font-bold">{formatPrice(quote.total_cents)}</p>
              {quote.days_remaining > 0 && (
                <p className="text-xs text-muted mt-1">
                  {quote.days_remaining === 1
                    ? "1 dia até a renovação"
                    : `${quote.days_remaining} dias até a renovação`}
                </p>
              )}
            </div>
            {paymentsRequired && (
              <span className="text-xs text-[var(--success)] bg-[var(--success)]/10 px-3 py-1 rounded-full">
                PIX
              </span>
            )}
          </div>
          <div className="border-t border-[var(--glass-border)] pt-3">
            <p className="text-muted text-sm">Mensalidade na renovação</p>
            <p className="text-lg font-bold">
              {formatPrice(quote.new_monthly_cents)}
              <span className="text-sm font-normal text-muted">/mês</span>
            </p>
            {quote.current_monthly_cents > 0 && (
              <p className="text-xs text-muted mt-1">
                Hoje {formatPrice(quote.current_monthly_cents)}/mês · acréscimo{" "}
                {formatPrice(quote.monthly_delta_cents)}/mês
              </p>
            )}
          </div>
        </div>
      )}

      {error && (
        <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-2 mt-4">
          {error}
        </p>
      )}

      <button
        type="button"
        disabled={loading || quoting || !hasChanges || quote === null}
        onClick={submit}
        className="btn-primary w-full !py-3 mt-6"
      >
        {loading ? <BusyLabel>Processando…</BusyLabel> : paymentsRequired ? "Pagar upgrade" : "Aplicar upgrade"}
      </button>
    </div>
  );
}
