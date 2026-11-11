"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { GamePreset, GameTypeInfo } from "@/lib/api";
import { formatBRL } from "@/lib/gameProvisionLabels";

type Props = {
  types: GameTypeInfo[];
  presets: GamePreset[];
  selectedType: string;
  selectedPresetId: number | null;
  onTypeChange: (slug: string) => void;
  onPresetChange: (id: number) => void;
  onQuote: (data: { game_type: string; preset_id: number }) => Promise<{
    total_cents: number;
    monthly_cents: number;
    slots: number;
    ram_mb: number;
  }>;
  children?: React.ReactNode;
};

export function GamePlanConfigurator({
  types,
  presets,
  selectedType,
  selectedPresetId,
  onTypeChange,
  onPresetChange,
  onQuote,
  children,
}: Props) {
  const [quote, setQuote] = useState<{
    total_cents: number;
    monthly_cents: number;
    slots: number;
    ram_mb: number;
  } | null>(null);
  const [loadingQuote, setLoadingQuote] = useState(false);

  const filteredPresets = useMemo(
    () => presets.filter((p) => p.game_type === selectedType),
    [presets, selectedType]
  );

  const selectedTypeInfo = types.find((t) => t.slug === selectedType);

  const refreshQuote = useCallback(async () => {
    if (!selectedPresetId) {
      setQuote(null);
      return;
    }
    setLoadingQuote(true);
    try {
      const q = await onQuote({ game_type: selectedType, preset_id: selectedPresetId });
      setQuote(q);
    } finally {
      setLoadingQuote(false);
    }
  }, [onQuote, selectedPresetId, selectedType]);

  useEffect(() => {
    refreshQuote();
  }, [refreshQuote]);

  useEffect(() => {
    if (filteredPresets.length && !filteredPresets.some((p) => p.id === selectedPresetId)) {
      const popular = filteredPresets.find((p) => p.is_popular) ?? filteredPresets[0];
      onPresetChange(popular.id);
    }
  }, [filteredPresets, selectedPresetId, onPresetChange]);

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-3 uppercase tracking-wide">
          Jogo
        </h3>
        <div className="grid sm:grid-cols-3 gap-3">
          {types.map((t) => (
            <button
              key={t.slug}
              type="button"
              onClick={() => onTypeChange(t.slug)}
              className={`text-left p-4 rounded-xl border transition ${
                selectedType === t.slug
                  ? "border-[var(--accent)] bg-[var(--accent)]/10"
                  : "border-[var(--glass-border)] hover:border-[var(--accent)]/40"
              }`}
            >
              <p className="font-bold">{t.label}</p>
              <p className="text-xs text-[var(--text-secondary)] mt-1 line-clamp-2">{t.description}</p>
            </button>
          ))}
        </div>
      </div>

      {selectedTypeInfo && (
        <p className="text-sm text-[var(--text-secondary)] -mt-4">{selectedTypeInfo.description}</p>
      )}

      <div>
        <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-3 uppercase tracking-wide">
          Plano
        </h3>
        <div className="grid sm:grid-cols-3 gap-3">
          {filteredPresets.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => onPresetChange(p.id)}
              className={`text-left p-4 rounded-xl border transition relative ${
                selectedPresetId === p.id
                  ? "border-[var(--accent)] bg-[var(--accent)]/10"
                  : "border-[var(--glass-border)] hover:border-[var(--accent)]/40"
              }`}
            >
              {p.is_popular && (
                <span className="absolute -top-2 right-3 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[var(--accent)] text-white">
                  Popular
                </span>
              )}
              <p className="font-bold">{p.name}</p>
              <p className="text-sm text-[var(--text-secondary)] mt-1">
                {p.slots} slots · {p.ram_mb / 1024} GB RAM
              </p>
              <p className="text-lg font-bold text-[var(--accent)] mt-2">{formatBRL(p.price_cents)}/mês</p>
            </button>
          ))}
        </div>
      </div>

      {children}

      <div className="glass-card p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <p className="text-sm text-[var(--text-secondary)]">Total mensal</p>
          <p className="text-2xl font-bold">
            {loadingQuote ? "..." : quote ? formatBRL(quote.total_cents) : "—"}
          </p>
          {quote && (
            <p className="text-xs text-[var(--text-muted)] mt-1">
              {quote.slots} slots · {quote.ram_mb / 1024} GB RAM
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
