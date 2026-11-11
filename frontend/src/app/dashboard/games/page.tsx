"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { GameServerCard } from "@/components/GameServerCard";
import { SvgGame, SvgPlus } from "@/components/ui/svgs";
import { api, type GameServer } from "@/lib/api";

export default function GameServersDashboardPage() {
  const router = useRouter();
  const [servers, setServers] = useState<GameServer[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const list = await api.gameServers();
      setServers(list);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const hasProvisioning = servers.some((s) => s.is_provisioning);
    const interval = setInterval(load, hasProvisioning ? 2000 : 10000);
    return () => clearInterval(interval);
  }, [servers]);

  const online = servers.filter((s) => s.status === "running").length;

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-10">
        <div>
          <p className="text-sm font-medium text-[var(--accent)] mb-2 tracking-wide uppercase">
            Game Hosting
          </p>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">Servidores de jogo</h1>
          <p className="text-secondary mt-2 max-w-lg">
            SA-MP, MTA, Minecraft e FiveM com painel de arquivos, start/stop e logs em tempo real.
          </p>
        </div>
        <button onClick={() => router.push("/order/game")} className="btn-primary shrink-0">
          <SvgPlus className="w-4 h-4" />
          Novo servidor
        </button>
      </div>

      {!loading && servers.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8">
          {[
            { label: "Total", value: servers.length },
            { label: "Online", value: online },
            { label: "Parados", value: servers.length - online },
          ].map((s) => (
            <div key={s.label} className="glass-card p-4 text-center">
              <p className="text-xs text-muted uppercase tracking-wider">{s.label}</p>
              <p className="text-2xl font-bold mt-1">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="grid md:grid-cols-2 gap-5">
          {[1, 2].map((i) => (
            <div key={i} className="glass-card p-6 h-64 shimmer rounded-2xl" />
          ))}
        </div>
      ) : servers.length === 0 ? (
        <div className="glass-card text-center py-20 px-6">
          <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-brand-400/20 to-brand-600/20 flex items-center justify-center">
            <SvgGame className="w-8 h-8 text-[var(--accent)]" />
          </div>
          <h2 className="text-xl font-semibold mb-2">Nenhum servidor de jogo</h2>
          <p className="text-muted mb-6 max-w-md mx-auto">
            Contrate hospedagem para SA-MP, MTA, Minecraft ou FiveM — com arquivos, start/stop e
            reinício no painel.
          </p>
          <button onClick={() => router.push("/order/game")} className="btn-primary">
            Contratar servidor de jogo
          </button>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-5">
          {servers.map((s) => (
            <GameServerCard key={s.id} server={s} />
          ))}
        </div>
      )}
    </>
  );
}
