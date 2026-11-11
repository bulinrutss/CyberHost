"use client";

import { useState } from "react";
import { WebDomainDnsHint } from "@/components/WebDomainDnsHint";
import { InfoTip } from "@/components/ui/InfoTip";
import { api, type VpsConnectionDomain, type VpsPortMapping } from "@/lib/api";

type Props = {
  instanceId: number;
  mappings: VpsPortMapping[];
  connections: VpsConnectionDomain[];
  dnsTarget: string;
  publicHost?: string | null;
  onUpdated: () => void;
};

export function VpsConnectionsPanel({
  instanceId,
  mappings,
  connections,
  dnsTarget,
  publicHost,
  onUpdated,
}: Props) {
  const [copied, setCopied] = useState<string | null>(null);
  const [domain, setDomain] = useState("");
  const [publicPort, setPublicPort] = useState<number>(() => mappings[0]?.public_port ?? 0);
  const [saving, setSaving] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [error, setError] = useState("");

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

  const saveDomain = async () => {
    if (!publicPort) {
      setError("Selecione uma porta pública.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.setVpsConnectionDomain(instanceId, {
        domain: domain.trim(),
        public_port: publicPort,
      });
      setDomain("");
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível salvar o domínio");
    } finally {
      setSaving(false);
    }
  };

  const removeDomain = async (connectionId: number) => {
    setRemovingId(connectionId);
    setError("");
    try {
      await api.deleteVpsConnectionDomain(instanceId, connectionId);
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível remover o domínio");
    } finally {
      setRemovingId(null);
    }
  };

  const labelForPort = (port: number) =>
    mappings.find((m) => m.public_port === port)?.label ?? `Porta pública ${port}`;

  return (
    <div className="space-y-4">
      <div className="glass-card w-full p-3 sm:p-4 border border-[var(--accent)]/20">
        <div className="mb-4">
          <p className="text-sm font-semibold inline-flex items-center gap-1.5">
            Portas de conexão
            <InfoTip>
              Público é o endereço para conectar de fora da rede. Interno é a porta no Windows.
              Copiar copia o endereço público (host e porta).
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

        {!mappings.length ? (
          <p className="text-sm text-secondary text-center py-6">
            Nenhuma porta pública configurada para este servidor ainda.
          </p>
        ) : (
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
                  const bound = connections.find((c) => c.public_port === m.public_port);
                  return (
                    <tr
                      key={key}
                      className="border-b border-[var(--glass-border)]/40 last:border-b-0 hover:bg-[var(--bg-elevated)]/30"
                    >
                      <td className="px-3 py-2.5">
                        <p className="font-medium leading-tight">{m.label}</p>
                        <p className="text-[10px] text-muted mt-0.5">:{m.internal_port}</p>
                        {bound && (
                          <p className="text-[10px] text-[var(--accent)] mt-1 font-mono break-all">
                            {bound.domain}
                            {bound.ssl_active ? " · HTTPS" : ""}
                          </p>
                        )}
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
        )}
      </div>

      {mappings.length > 0 && (
        <div className="glass-card w-full p-6 space-y-4">
          <div>
            <h3 className="font-semibold inline-flex items-center gap-1.5">
              Domínio personalizado
              <InfoTip>
                Aponte o DNS do seu domínio para o IP do painel. Em portas web (HTTP/HTTPS), o
                tráfego passa pelo domínio com certificado automático. Em RDP e jogos, use
                domínio:porta pública após o DNS propagar.
              </InfoTip>
            </h3>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Escolha a porta pública e cadastre o domínio ou subdomínio, como na hospedagem de
              sites.
            </p>
          </div>

          {error && (
            <div
              className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-400"
              role="alert"
            >
              {error}
            </div>
          )}

          <label className="block text-sm">
            <span className="text-muted">Porta pública</span>
            <select
              className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
              value={publicPort || ""}
              onChange={(e) => setPublicPort(Number(e.target.value))}
            >
              {mappings.map((m) => (
                <option key={m.public_port} value={m.public_port}>
                  {m.label} — {m.connection_address}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="text-muted">Domínio ou subdomínio</span>
            <input
              type="text"
              className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
              placeholder="app.seudominio.com.br"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
            <p className="mt-2 text-xs text-muted leading-relaxed">
              Pode usar um subdomínio que ainda não esteja cadastrado (ex.:{" "}
              <code className="text-[var(--accent)]">app.seudominio.com</code>) mesmo que o domínio
              raiz ou outro subdomínio já esteja em uso em outro serviço — o que importa é o
              endereço completo.
            </p>
            <WebDomainDnsHint dnsTarget={dnsTarget} compact />
          </label>

          <button
            type="button"
            className="btn-ghost !py-2"
            disabled={saving || !domain.trim()}
            onClick={() => void saveDomain()}
          >
            {saving ? "Salvando…" : "Salvar domínio"}
          </button>

          {connections.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-[var(--glass-border)]/50">
              <p className="text-sm font-medium">Domínios cadastrados</p>
              {connections.map((conn) => (
                <div
                  key={conn.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]/50 px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="font-mono text-sm text-[var(--accent)] break-all">{conn.domain}</p>
                    <p className="text-xs text-muted mt-0.5 leading-relaxed">
                      {labelForPort(conn.public_port)} · pública {conn.public_port}
                      {conn.http_proxy
                        ? conn.ssl_active
                          ? " · proxy HTTPS ativo"
                          : " · proxy HTTP (SSL após DNS)"
                        : ` · use ${conn.domain}:${conn.public_port}`}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn-ghost !py-1 !px-2.5 text-xs text-red-300"
                    disabled={removingId === conn.id}
                    onClick={() => void removeDomain(conn.id)}
                  >
                    {removingId === conn.id ? "Removendo…" : "Remover"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
