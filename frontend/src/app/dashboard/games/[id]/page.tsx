"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { GameServerPanel } from "@/components/GameServerPanel";
import { ProvisionProgress } from "@/components/ProvisionProgress";
import { api, type GameServer } from "@/lib/api";

export default function GameServerDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const [server, setServer] = useState<GameServer | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const s = await api.gameServer(id);
      setServer(s);
    } catch {
      router.push("/dashboard/games");
    } finally {
      setLoading(false);
    }
  }, [id, router]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!server?.is_provisioning) return;
    const interval = setInterval(load, 2000);
    return () => clearInterval(interval);
  }, [server?.is_provisioning, load]);

  if (loading || !server) {
    return <div className="glass-card p-12 shimmer h-64 rounded-2xl" />;
  }

  return (
    <>
      <div className="mb-8">
        <Link href="/dashboard/games" className="text-sm text-[var(--accent)] hover:underline">
          ← Servidores de jogo
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mt-4">
          <div>
            <p className="text-sm font-medium text-[var(--accent)]">{server.game_label}</p>
            <h1 className="text-3xl font-bold">{server.server_name}</h1>
            <p className="font-mono text-secondary mt-1">{server.address}</p>
          </div>
        </div>
      </div>

      {server.is_provisioning ? (
        <div className="glass-card p-8 text-center">
          <ProvisionProgress progress={0} label="Provisionando servidor..." />
          <p className="text-sm text-muted mt-4">Aguarde alguns instantes...</p>
        </div>
      ) : (
        <GameServerPanel server={server} onRefresh={load} />
      )}
    </>
  );
}
