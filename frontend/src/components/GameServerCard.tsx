"use client";

import Link from "next/link";
import { SvgArrowRight } from "@/components/ui/svgs";
import { ProvisionProgress } from "@/components/ProvisionProgress";
import type { GameServer } from "@/lib/api";

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

export function GameServerCard({ server }: { server: GameServer }) {
  const isRunning = server.status === "running";

  return (
    <Link href={`/dashboard/games/${server.id}`} className="group block">
      <article className="glass-card p-6 transition-all duration-300 hover:border-[var(--accent)]/50 hover:shadow-[0_8px_32px_var(--accent-glow)]">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`status-dot shrink-0 ${statusClass(server.status)}`} />
            <div className="min-w-0">
              <p className="text-xs font-medium text-[var(--accent)] uppercase tracking-wide">
                {server.game_label}
              </p>
              <h3 className="font-bold text-lg truncate group-hover:text-[var(--accent)] transition-colors">
                {server.server_name}
              </h3>
              <p className="text-sm font-mono text-secondary mt-0.5">{server.address}</p>
            </div>
          </div>
          <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-[var(--glass-bg)] border border-[var(--glass-border)]">
            {statusLabel(server.status)}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-5">
          <div className="text-center p-3 rounded-xl glass">
            <p className="text-xs text-muted">Slots</p>
            <p className="text-lg font-bold">{server.slots}</p>
          </div>
          <div className="text-center p-3 rounded-xl glass">
            <p className="text-xs text-muted">RAM</p>
            <p className="text-lg font-bold">{server.ram_mb / 1024} GB</p>
          </div>
          <div className="text-center p-3 rounded-xl glass">
            <p className="text-xs text-muted">Porta</p>
            <p className="text-lg font-bold">{server.port}</p>
          </div>
        </div>

        {server.is_provisioning ? (
          <ProvisionProgress compact progress={0} label="Provisionando..." className="mb-1" />
        ) : (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted">{isRunning ? "Servidor ativo" : "Clique para gerenciar"}</span>
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
