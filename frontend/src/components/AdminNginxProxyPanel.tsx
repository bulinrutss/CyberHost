"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { InlineLoader } from "@/components/PageLoader";
import { api, type NginxProxyEntry, type NginxProxyMode } from "@/lib/api";

const KIND_LABEL: Record<NginxProxyEntry["kind"], string> = {
  manual: "Manual",
  web_site: "Site",
  vps_connection: "VPS",
};

const MODE_LABEL: Record<NginxProxyMode, string> = {
  reverse_proxy: "Proxy reverso",
  redirect: "Redirecionamento",
};

type ManualForm = {
  domain: string;
  mode: NginxProxyMode;
  upstream_url: string;
  redirect_url: string;
  include_www: boolean;
  notes: string;
};

const emptyForm = (): ManualForm => ({
  domain: "",
  mode: "reverse_proxy",
  upstream_url: "http://127.0.0.1:30000/",
  redirect_url: "https://",
  include_www: false,
  notes: "",
});

export function AdminNginxProxyPanel() {
  const [entries, setEntries] = useState<NginxProxyEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [form, setForm] = useState<ManualForm>(emptyForm);
  const [editing, setEditing] = useState<NginxProxyEntry | null>(null);
  const [editDomain, setEditDomain] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await api.adminNginxProxies());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar proxies");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const createManual = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.adminCreateNginxProxy({
        domain: form.domain.trim(),
        mode: form.mode,
        upstream_url: form.mode === "reverse_proxy" ? form.upstream_url.trim() : undefined,
        redirect_url: form.mode === "redirect" ? form.redirect_url.trim() : undefined,
        include_www: form.include_www,
        notes: form.notes.trim() || undefined,
      });
      setMessage("Proxy criado e nginx recarregado.");
      setForm(emptyForm());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar proxy");
    } finally {
      setSaving(false);
    }
  };

  const saveManualEdit = async () => {
    if (!editing || editing.kind !== "manual" || !editing.reference_id) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.adminUpdateNginxProxy(editing.reference_id, {
        domain: form.domain.trim(),
        mode: form.mode,
        upstream_url: form.mode === "reverse_proxy" ? form.upstream_url.trim() : undefined,
        redirect_url: form.mode === "redirect" ? form.redirect_url.trim() : undefined,
        include_www: form.include_www,
        notes: form.notes.trim() || undefined,
      });
      setMessage("Proxy atualizado.");
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao atualizar proxy");
    } finally {
      setSaving(false);
    }
  };

  const saveSystemDomain = async (entry: NginxProxyEntry) => {
    if (!entry.reference_id) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.adminUpdateSystemNginxProxy(entry.kind, entry.reference_id, editDomain.trim());
      setMessage("Domínio atualizado.");
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao atualizar domínio");
    } finally {
      setSaving(false);
    }
  };

  const removeEntry = async (entry: NginxProxyEntry) => {
    if (!entry.deletable || !entry.reference_id) return;
    const label = entry.domain;
    if (!window.confirm(`Remover o proxy de ${label}?`)) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      if (entry.kind === "manual") {
        await api.adminDeleteNginxProxy(entry.reference_id);
      } else {
        await api.adminDeleteSystemNginxProxy(entry.kind, entry.reference_id);
      }
      setMessage("Proxy removido.");
      if (editing?.key === entry.key) setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao remover proxy");
    } finally {
      setSaving(false);
    }
  };

  const openManualEdit = (entry: NginxProxyEntry) => {
    setEditing(entry);
    setForm({
      domain: entry.domain,
      mode: entry.mode,
      upstream_url: entry.mode === "reverse_proxy" ? entry.target : "http://127.0.0.1:30000/",
      redirect_url: entry.mode === "redirect" ? entry.target : "https://",
      include_www: entry.include_www,
      notes: entry.notes || "",
    });
  };

  const openSystemEdit = (entry: NginxProxyEntry) => {
    setEditing(entry);
    setEditDomain(entry.domain);
  };

  return (
    <div className="space-y-6">
      {error && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-400">
          {error}
        </div>
      )}
      {message && (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-400">
          {message}
        </div>
      )}

      <div className="glass-card p-6 space-y-4">
        <div>
          <h3 className="font-semibold">Novo proxy manual</h3>
          <p className="text-sm text-muted mt-1">
            Cria um vhost nginx independente. Sites e VPS continuam sendo geridos automaticamente,
            mas aparecem na lista abaixo.
          </p>
        </div>
        <form onSubmit={(e) => void createManual(e)} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm">
              <span className="text-muted">Domínio</span>
              <input
                className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
                value={form.domain}
                onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}
                placeholder="app.exemplo.com"
                required
              />
            </label>
            <label className="block text-sm">
              <span className="text-muted">Tipo</span>
              <select
                className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
                value={form.mode}
                onChange={(e) =>
                  setForm((f) => ({ ...f, mode: e.target.value as NginxProxyMode }))
                }
              >
                <option value="reverse_proxy">Proxy reverso</option>
                <option value="redirect">Redirecionamento 301</option>
              </select>
            </label>
          </div>
          {form.mode === "reverse_proxy" ? (
            <label className="block text-sm">
              <span className="text-muted">Destino (upstream)</span>
              <input
                className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] font-mono text-sm"
                value={form.upstream_url}
                onChange={(e) => setForm((f) => ({ ...f, upstream_url: e.target.value }))}
                placeholder="http://127.0.0.1:30001/"
                required
              />
            </label>
          ) : (
            <label className="block text-sm">
              <span className="text-muted">Redirecionar para</span>
              <input
                className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] font-mono text-sm"
                value={form.redirect_url}
                onChange={(e) => setForm((f) => ({ ...f, redirect_url: e.target.value }))}
                placeholder="https://destino.com/"
                required
              />
            </label>
          )}
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={form.include_www}
              onChange={(e) => setForm((f) => ({ ...f, include_www: e.target.checked }))}
            />
            Incluir www no certificado e no vhost
          </label>
          <label className="block text-sm">
            <span className="text-muted">Notas (opcional)</span>
            <input
              className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </label>
          <button type="submit" className="btn-primary !py-2" disabled={saving}>
            {saving ? "Salvando…" : "Adicionar proxy"}
          </button>
        </form>
      </div>

      <div className="glass-card p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h3 className="font-semibold">Domínios e redirecionamentos</h3>
          <button type="button" className="btn-ghost !py-1.5 text-sm" onClick={() => void load()}>
            Atualizar
          </button>
        </div>

        {loading ? (
          <InlineLoader label="Carregando proxies…" />
        ) : !entries.length ? (
          <p className="text-sm text-muted text-center py-8">Nenhum proxy cadastrado.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)]/60">
            <table className="w-full text-sm min-w-[760px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-muted border-b border-[var(--glass-border)]/60 bg-[var(--bg-elevated)]/40">
                  <th className="px-3 py-2 font-medium">Domínio</th>
                  <th className="px-3 py-2 font-medium">Origem</th>
                  <th className="px-3 py-2 font-medium">Tipo</th>
                  <th className="px-3 py-2 font-medium">Destino</th>
                  <th className="px-3 py-2 font-medium">SSL</th>
                  <th className="px-3 py-2 font-medium w-40">Ações</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.key}
                    className="border-b border-[var(--glass-border)]/40 last:border-b-0 hover:bg-[var(--bg-elevated)]/30"
                  >
                    <td className="px-3 py-2.5">
                      <p className="font-mono text-[var(--accent)] break-all">{entry.domain}</p>
                      {entry.notes && (
                        <p className="text-[10px] text-muted mt-0.5">{entry.notes}</p>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <p>{KIND_LABEL[entry.kind]}</p>
                      <p className="text-[10px] text-muted mt-0.5">{entry.label}</p>
                      {entry.kind === "web_site" && entry.reference_id && (
                        <Link
                          href={`/admin/sites/${entry.reference_id}`}
                          className="text-[10px] text-[var(--accent)] hover:underline"
                        >
                          Abrir site
                        </Link>
                      )}
                      {entry.kind === "vps_connection" && (
                        <span className="text-[10px] text-muted block">via painel do cliente</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5">{MODE_LABEL[entry.mode]}</td>
                    <td className="px-3 py-2.5">
                      <p className="font-mono text-xs break-all">{entry.target}</p>
                    </td>
                    <td className="px-3 py-2.5">
                      {entry.ssl_active ? (
                        <span className="text-emerald-400 text-xs">Ativo</span>
                      ) : (
                        <span className="text-muted text-xs">HTTP</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {entry.kind === "manual" && (
                          <button
                            type="button"
                            className="btn-ghost !py-1 !px-2 text-xs"
                            disabled={saving}
                            onClick={() => openManualEdit(entry)}
                          >
                            Editar
                          </button>
                        )}
                        {entry.editable && entry.kind !== "manual" && (
                          <button
                            type="button"
                            className="btn-ghost !py-1 !px-2 text-xs"
                            disabled={saving}
                            onClick={() => openSystemEdit(entry)}
                          >
                            Editar
                          </button>
                        )}
                        {entry.deletable && (
                          <button
                            type="button"
                            className="btn-ghost !py-1 !px-2 text-xs text-red-300"
                            disabled={saving}
                            onClick={() => void removeEntry(entry)}
                          >
                            Remover
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <div className="glass-card p-6 space-y-4 border border-[var(--accent)]/30">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold">
              Editar {editing.kind === "manual" ? "proxy manual" : "domínio"}
            </h3>
            <button type="button" className="btn-ghost !py-1 text-xs" onClick={() => setEditing(null)}>
              Fechar
            </button>
          </div>

          {editing.kind === "manual" ? (
            <div className="space-y-4">
              <label className="block text-sm">
                <span className="text-muted">Domínio</span>
                <input
                  className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
                  value={form.domain}
                  onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}
                />
              </label>
              <label className="block text-sm">
                <span className="text-muted">Tipo</span>
                <select
                  className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
                  value={form.mode}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, mode: e.target.value as NginxProxyMode }))
                  }
                >
                  <option value="reverse_proxy">Proxy reverso</option>
                  <option value="redirect">Redirecionamento 301</option>
                </select>
              </label>
              {form.mode === "reverse_proxy" ? (
                <label className="block text-sm">
                  <span className="text-muted">Destino</span>
                  <input
                    className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] font-mono text-sm"
                    value={form.upstream_url}
                    onChange={(e) => setForm((f) => ({ ...f, upstream_url: e.target.value }))}
                  />
                </label>
              ) : (
                <label className="block text-sm">
                  <span className="text-muted">Redirecionar para</span>
                  <input
                    className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] font-mono text-sm"
                    value={form.redirect_url}
                    onChange={(e) => setForm((f) => ({ ...f, redirect_url: e.target.value }))}
                  />
                </label>
              )}
              <button
                type="button"
                className="btn-primary !py-2"
                disabled={saving}
                onClick={() => void saveManualEdit()}
              >
                {saving ? "Salvando…" : "Salvar alterações"}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <label className="block text-sm">
                <span className="text-muted">Domínio</span>
                <input
                  className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
                  value={editDomain}
                  onChange={(e) => setEditDomain(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn-primary !py-2"
                disabled={saving}
                onClick={() => void saveSystemDomain(editing)}
              >
                {saving ? "Salvando…" : "Salvar domínio"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
