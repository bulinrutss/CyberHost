"use client";

import { MetricRing } from "@/components/ui/MetricRing";
import { InfoTip } from "@/components/ui/InfoTip";
import { SvgChip, SvgDisk, SvgMemory } from "@/components/ui/svgs";
import type { VpsMetrics } from "@/lib/api";

function formatUptime(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

type Props = {
  metrics: VpsMetrics;
  powerState: string;
};

export function VpsMetricsPanel({ metrics, powerState }: Props) {
  const isOn = powerState === "poweredOn";
  const ramGb = (metrics.ram_allocated_mb / 1024).toFixed(1);
  const ramUsedGb =
    metrics.ram_used_mb != null ? (metrics.ram_used_mb / 1024).toFixed(1) : null;

  const diskHint =
    metrics.disk_source === "guest"
      ? metrics.disk_free_gb != null
        ? `${metrics.disk_free_gb} GB livres no Windows`
        : "uso dentro do Windows"
      : metrics.disk_source === "storage"
        ? "capacidade provisionada"
        : "capacidade do disco virtual";

  const specs = [
    {
      label: "vCPU",
      value: `${metrics.cpu_allocated}`,
      hint: "núcleos alocados",
    },
    {
      label: "RAM",
      value: `${ramGb} GB`,
      hint: ramUsedGb ? `${ramUsedGb} GB ativa (guest)` : "alocado",
    },
    {
      label: "Disco",
      value: metrics.disk_allocated_gb != null ? `${metrics.disk_allocated_gb} GB` : "—",
      hint:
        metrics.disk_used_gb != null
          ? `${metrics.disk_used_gb} GB usados · ${diskHint}`
          : diskHint,
    },
    {
      label: "Uptime",
      value: formatUptime(metrics.uptime_seconds),
      hint: isOn ? "tempo ligada" : "VM desligada",
    },
  ];

  return (
    <div className="glass-card p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
        <div>
          <h2 className="text-lg font-semibold inline-flex items-center gap-1.5">
            Recursos & uso
            <InfoTip>
              CPU, memória e disco mostram o uso agora. Os anéis só atualizam com o
              servidor ligado. O disco é o espaço dentro do Windows; se o uso interno
              não estiver disponível, aparece só o tamanho do disco virtual.
            </InfoTip>
          </h2>
          <p className="text-sm text-muted mt-1">
            Métricas em tempo real
          </p>
        </div>
        {!isOn && (
          <span className="text-xs px-3 py-1 rounded-full glass text-muted">
            Uso disponível com VM ligada
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 mb-8">
        <MetricRing
          label="CPU"
          value={isOn ? metrics.cpu_usage_percent : null}
          sublabel={`${metrics.cpu_allocated} vCPU`}
          svg={<SvgChip className="w-4 h-4" />}
        />
        <MetricRing
          label="Memória"
          value={isOn ? metrics.ram_usage_percent : null}
          sublabel={
            ramUsedGb ? `${ramUsedGb} / ${ramGb} GB` : `${ramGb} GB total`
          }
          svg={<SvgMemory className="w-4 h-4" />}
        />
        <MetricRing
          label="Disco"
          value={metrics.disk_usage_percent}
          sublabel={
            metrics.disk_allocated_gb != null
              ? metrics.disk_source === "guest"
                ? `${metrics.disk_used_gb ?? "—"} / ${metrics.disk_allocated_gb} GB`
                : `${metrics.disk_allocated_gb} GB total`
              : "capacidade"
          }
          svg={<SvgDisk className="w-4 h-4" />}
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {specs.map((s) => (
          <div key={s.label} className="rounded-xl p-4 glass border border-[var(--glass-border)]">
            <p className="text-xs text-muted uppercase tracking-wider">{s.label}</p>
            <p className="text-xl font-bold mt-1">{s.value}</p>
            <p className="text-xs text-secondary mt-0.5">{s.hint}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
