"use client";

import Link from "next/link";
import { SvgArrowRight } from "@/components/ui/svgs";
import { PowerStateBadge } from "@/components/PowerStateBadge";
import { ProvisionProgress } from "@/components/ProvisionProgress";
import { VpsStatusBadge } from "@/components/VpsStatusBadge";
import type { VpsInstanceList } from "@/lib/api";

function MiniBar({ label, value }: { label: string; value: number | null | undefined }) {
  const pct = value ?? 0;
  const hasValue = value != null;

  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted">{label}</span>
        <span className="font-medium">{hasValue ? `${pct}%` : "—"}</span>
      </div>
      <div className="metric-bar-track">
        <div
          className="metric-bar-fill"
          style={{ width: hasValue ? `${Math.min(pct, 100)}%` : "0%" }}
        />
      </div>
    </div>
  );
}

export function VpsCard({ vps }: { vps: VpsInstanceList }) {
  const isOn = vps.power_state === "poweredOn";
  const isProvisioning = vps.is_provisioning;

  return (
    <Link href={`/dashboard/vps/${vps.id}`} className="group block">
      <article className="glass-card p-6 transition-all duration-300 hover:border-[var(--accent)]/50 hover:shadow-[0_8px_32px_var(--accent-glow)]">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`status-dot shrink-0 ${isOn ? "status-dot-on" : "status-dot-off"}`} />
            <div className="min-w-0">
              <h3 className="font-bold text-lg truncate group-hover:text-[var(--accent)] transition-colors">
                {vps.vm_name}
              </h3>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <PowerStateBadge powerState={vps.power_state} />
            <VpsStatusBadge status={vps.status} />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-5">
          <div className="text-center p-3 rounded-xl glass">
            <p className="text-xs text-muted">vCPU</p>
            <p className="text-lg font-bold">{vps.vcpu}</p>
          </div>
          <div className="text-center p-3 rounded-xl glass">
            <p className="text-xs text-muted">RAM</p>
            <p className="text-lg font-bold">{vps.ram_mb / 1024} GB</p>
          </div>
          <div className="text-center p-3 rounded-xl glass">
            <p className="text-xs text-muted">Disco</p>
            <p className="text-lg font-bold">
              {vps.disk_allocated_gb != null ? `${vps.disk_allocated_gb}` : "—"}
              {vps.disk_allocated_gb != null && (
                <span className="text-xs font-normal text-muted"> GB</span>
              )}
            </p>
          </div>
        </div>

        {isProvisioning ? (
          <ProvisionProgress
            compact
            progress={vps.provision_progress ?? 0}
            label={vps.provision_label}
            className="mb-1"
          />
        ) : (
          <div className="space-y-2.5">
            <MiniBar label="CPU" value={isOn ? vps.cpu_usage_percent : null} />
            <MiniBar label="RAM" value={isOn ? vps.ram_usage_percent : null} />
            <MiniBar label="Disco" value={vps.disk_usage_percent} />
          </div>
        )}

        {vps.error_message && (
          <p className="text-xs text-[var(--danger)] mt-4 line-clamp-2">{vps.error_message}</p>
        )}

        <p className="inline-flex items-center gap-1 text-xs text-muted mt-4 group-hover:text-[var(--accent)] transition-colors">
          {isProvisioning ? "Acompanhar criação" : "Gerenciar servidor"}
          <SvgArrowRight className="w-3.5 h-3.5" />
        </p>
      </article>
    </Link>
  );
}
