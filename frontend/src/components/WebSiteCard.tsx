"use client";

import Link from "next/link";
import { SvgArrowRight } from "@/components/ui/svgs";
import { ProvisionProgress } from "@/components/ProvisionProgress";
import type { WebSite } from "@/lib/api";

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    running: "Online",
    stopped: "Parado",
    starting: "Iniciando",
    stopping: "Parando",
    creating: "Criando",
    error: "Erro",
  };
  return map[status] ?? status;
}

function statusClass(status: string): string {
  if (status === "running") return "status-dot-on";
  if (status === "creating" || status === "starting") return "status-dot-on animate-pulse";
  return "status-dot-off";
}

function ramLabel(mb: number): string {
  return mb >= 1024 ? `${mb / 1024} GB` : `${mb} MB`;
}

export function WebSiteCard({ site }: { site: WebSite }) {
  const isRunning = site.status === "running";

  return (
    <Link href={`/dashboard/sites/${site.id}`} className="group block">
      <article className="glass-card p-6 transition-all duration-300 hover:border-[var(--accent)]/50 hover:shadow-[0_8px_32px_var(--accent-glow)]">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`status-dot shrink-0 ${statusClass(site.status)}`} />
            <div className="min-w-0">
              <p className="text-xs font-medium text-[var(--accent)] uppercase tracking-wide">
                {site.php_enabled ? "PHP" : "Estático"}
              </p>
              <h3 className="font-bold text-lg truncate group-hover:text-[var(--accent)] transition-colors">
                {site.domain || site.site_slug}
              </h3>
              <p className="text-xs font-mono text-secondary mt-0.5 truncate">{site.public_url}</p>
            </div>
          </div>
          <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-[var(--glass-bg)] border border-[var(--glass-border)]">
            {statusLabel(site.status)}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-5">
          <div className="text-center p-3 rounded-xl glass">
            <p className="text-xs text-muted">RAM</p>
            <p className="text-lg font-bold">{ramLabel(site.ram_mb)}</p>
          </div>
          <div className="text-center p-3 rounded-xl glass">
            <p className="text-xs text-muted">Disco</p>
            <p className="text-lg font-bold">{site.disk_mb >= 1024 ? `${site.disk_mb / 1024} GB` : `${site.disk_mb} MB`}</p>
          </div>
        </div>

        {site.is_provisioning ? (
          <ProvisionProgress compact progress={0} label="Publicando..." className="mb-1" />
        ) : (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted">{isRunning ? "Site no ar" : "Clique para gerenciar"}</span>
            <span className="inline-flex items-center gap-1 text-[var(--accent)] font-medium group-hover:gap-2 transition-all">
              Abrir
              <SvgArrowRight />
            </span>
          </div>
        )}
      </article>
    </Link>
  );
}
