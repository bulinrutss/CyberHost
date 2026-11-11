"use client";

import { useState } from "react";
import type { VpsPortMapping } from "@/lib/api";
import { InfoTip } from "@/components/ui/InfoTip";

type Props = {
  mappings: VpsPortMapping[];
  publicHost?: string | null;
};

export function VpsPortsPanel({ mappings, publicHost }: Props) {
  const [copied, setCopied] = useState<string | null>(null);

  const copy = async (key: string, value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      /* ignore */
    }
  };

  if (!mappings.length) {
    return (
      <div className="glass-card p-8 text-center text-secondary text-sm max-w-lg mx-auto">
        <p className="inline-flex items-center justify-center gap-1.5">
          Nenhuma porta pública configurada para este servidor ainda.
          <InfoTip>
            Quando o servidor estiver pronto, as portas públicas (RDP e outras)
            aparecem aqui para conectar de fora da rede.
          </InfoTip>
        </p>
      </div>
    );
  }

  return (
    <div className="glass-card w-full p-3 sm:p-4 border border-[var(--accent)]/20">
      <div className="mb-4">
        <p className="text-sm font-semibold inline-flex items-center gap-1.5">
          Portas de conexão
          <InfoTip>
            Público é o endereço para conectar de fora da rede. Interno é a porta no
            Windows. Copiar copia o endereço público (host e porta).
          </InfoTip>
        </p>
        <p className="text-[11px] text-muted mt-1 leading-snug">
          Use o endereço público abaixo para conectar de fora da rede.
          {publicHost && (
            <>
              {" "}
              IP público: <span className="font-mono text-secondary">{publicHost}</span>.
            </>
          )}
        </p>
      </div>

      <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)]/60">
        <table className="w-full text-sm min-w-[520px]">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-muted border-b border-[var(--glass-border)]/60 bg-[var(--bg-elevated)]/40">
              <th className="px-3 py-2 font-medium">Serviço</th>
              <th className="px-3 py-2 font-medium">Público</th>
              <th className="px-3 py-2 font-medium">Interno</th>
              <th className="px-3 py-2 font-medium w-24">Copiar</th>
            </tr>
          </thead>
          <tbody>
            {mappings.map((m) => {
              const key = `${m.public_port}-${m.internal_port}`;
              return (
                <tr
                  key={key}
                  className="border-b border-[var(--glass-border)]/40 last:border-b-0 hover:bg-[var(--bg-elevated)]/30"
                >
                  <td className="px-3 py-2.5">
                    <p className="font-medium leading-tight">{m.label}</p>
                    <p className="text-[10px] text-muted mt-0.5">:{m.internal_port}</p>
                  </td>
                  <td className="px-3 py-2.5">
                    <p className="font-mono text-[var(--accent)] font-semibold break-all">
                      {m.connection_address}
                    </p>
                  </td>
                  <td className="px-3 py-2.5">
                    <p className="font-mono text-secondary">{m.internal_port}</p>
                  </td>
                  <td className="px-3 py-2.5">
                    <button
                      type="button"
                      className="btn-ghost !py-1 !px-2.5 text-xs"
                      onClick={() => copy(key, m.connection_address)}
                    >
                      {copied === key ? "Copiado" : "Copiar"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
