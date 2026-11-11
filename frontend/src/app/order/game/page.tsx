"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { GamePlanConfigurator } from "@/components/GamePlanConfigurator";
import { PageShell } from "@/components/ui/PageShell";
import { api, getToken, type GamePreset, type GameTypeInfo } from "@/lib/api";

export default function GameOrderPage() {
  const router = useRouter();
  const [types, setTypes] = useState<GameTypeInfo[]>([]);
  const [presets, setPresets] = useState<GamePreset[]>([]);
  const [selectedType, setSelectedType] = useState("samp");
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);
  const [serverName, setServerName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.gameTypes().then((t) => {
      setTypes(t);
      if (t.length) setSelectedType(t[0].slug);
    });
    api.gamePresets().then(setPresets);
  }, [router]);

  const onQuote = useCallback(
    (data: { game_type: string; preset_id: number }) => api.gameQuote(data),
    []
  );

  const submit = async () => {
    if (!serverName.trim()) {
      setError("Informe o nome do servidor");
      return;
    }
    if (!selectedPresetId) {
      setError("Selecione um plano");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const order = await api.createGameOrder({
        game_type: selectedType,
        preset_id: selectedPresetId,
        server_name: serverName.trim(),
      });
      router.push(`/order/game/complete?order=${order.id}`);
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
          <h1 className="text-3xl font-bold mt-4">Contratar servidor de jogo</h1>
          <p className="text-[var(--text-secondary)] mt-2">
            Hospedagem com painel de arquivos, start/stop e logs — SA-MP, MTA, Minecraft e FiveM.
            Diferente da VPS Windows, você não gerencia o sistema operacional.
          </p>
        </div>

        {types.length > 0 && (
          <GamePlanConfigurator
            types={types}
            presets={presets}
            selectedType={selectedType}
            selectedPresetId={selectedPresetId}
            onTypeChange={setSelectedType}
            onPresetChange={setSelectedPresetId}
            onQuote={onQuote}
          >
            <div>
              <label className="block text-sm font-semibold text-[var(--text-secondary)] mb-2 uppercase tracking-wide">
                Nome do servidor
              </label>
              <input
                type="text"
                value={serverName}
                onChange={(e) => setServerName(e.target.value)}
                placeholder="Meu servidor RP"
                className="w-full px-4 py-3 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
                maxLength={63}
              />
            </div>
          </GamePlanConfigurator>
        )}

        {error && (
          <p className="text-red-400 text-sm mt-4">{error}</p>
        )}

        <div className="mt-8 flex flex-col sm:flex-row gap-3">
          <button
            type="button"
            onClick={submit}
            disabled={loading || !selectedPresetId}
            className="btn-primary flex-1"
          >
            {loading ? "Processando..." : "Contratar servidor"}
          </button>
          <Link href="/order" className="btn-ghost text-center">
            Preciso de VPS Windows
          </Link>
        </div>
      </div>
    </PageShell>
  );
}
