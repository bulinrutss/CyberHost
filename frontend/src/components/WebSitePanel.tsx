"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WebDomainDnsHint } from "@/components/WebDomainDnsHint";
import { WebPageBuilderPanel } from "@/components/WebPageBuilderPanel";
import { WebSiteAnalyticsPanel } from "@/components/WebSiteAnalyticsPanel";
import { SvgDocument, SvgFolder, SvgRefresh, SvgTrash, SvgUpload } from "@/components/ui/svgs";
import { collectFilesFromFileList, uploadDisplayName, type FileUploadEntry } from "@/lib/cloudFiles";
import { WebSiteRenewalPanel } from "@/components/WebSiteRenewalPanel";
import { api, formatPrice, type GameFileEntry, type WebSite } from "@/lib/api";

function formatBytes(n: number) {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

type TabId = "overview" | "builder" | "stats" | "files" | "logs" | "billing";

type Props = {
  site: WebSite;
  onRefresh: () => void;
  admin?: boolean;
  initialTab?: TabId;
};

export function WebSitePanel({ site, onRefresh, admin = false, initialTab }: Props) {
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [files, setFiles] = useState<GameFileEntry[]>([]);
  const [currentPath, setCurrentPath] = useState("");
  const [editorPath, setEditorPath] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [domain, setDomain] = useState(site.domain ?? "");
  const [error, setError] = useState("");
  const [uploadNotice, setUploadNotice] = useState("");
  const [tab, setTab] = useState<TabId>(
    initialTab ?? (site.php_enabled ? "overview" : "builder")
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const loadLogs = useCallback(async () => {
    const res = admin
      ? await api.adminWebSiteLogs(site.id, 150)
      : await api.webSiteLogs(site.id, 150);
    setLogs(res.lines || "(sem logs ainda)");
  }, [admin, site.id]);

  const loadFiles = useCallback(async () => {
    const list = admin
      ? await api.adminWebSiteFiles(site.id, currentPath)
      : await api.webSiteFiles(site.id, currentPath);
    setFiles(list);
    onRefresh();
  }, [admin, site.id, currentPath, onRefresh]);

  useEffect(() => {
    if (tab === "logs") void loadLogs();
  }, [tab, loadLogs]);

  useEffect(() => {
    if (tab === "files") void loadFiles();
  }, [tab, loadFiles, currentPath]);

  useEffect(() => {
    setDomain(site.domain ?? "");
  }, [site.domain]);

  const pathParts = currentPath ? currentPath.split("/").filter(Boolean) : [];
  const quotaBytes = Math.max(1, site.disk_mb * 1024 * 1024);
  const usedBytes = site.data_used_bytes ?? 0;
  const quotaPercent = Math.min(100, Math.round((usedBytes / quotaBytes) * 100));

  const goToPath = (index: number) => {
    if (index < 0) {
      setCurrentPath("");
      return;
    }
    setCurrentPath(pathParts.slice(0, index + 1).join("/"));
  };

  const runAction = async (action: "start" | "stop" | "restart") => {
    setActionLoading(action);
    setError("");
    try {
      if (action === "start") {
        if (admin) await api.adminStartWebSite(site.id);
        else await api.startWebSite(site.id);
      } else if (action === "stop") {
        if (admin) await api.adminStopWebSite(site.id);
        else await api.stopWebSite(site.id);
      } else if (admin) await api.adminRestartWebSite(site.id);
      else await api.restartWebSite(site.id);
      onRefresh();
      if (tab === "logs") await loadLogs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro na ação");
    } finally {
      setActionLoading(null);
    }
  };

  const saveDomain = async () => {
    setActionLoading("domain");
    setError("");
    try {
      if (admin) await api.adminUpdateWebSiteDomain(site.id, domain.trim() || null);
      else await api.updateWebSiteDomain(site.id, domain.trim() || null);
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível atualizar o domínio");
    } finally {
      setActionLoading(null);
    }
  };

  const openFile = async (path: string) => {
    setError("");
    try {
      const res = admin
        ? await api.adminWebSiteFileContent(site.id, path)
        : await api.webSiteFileContent(site.id, path);
      setEditorPath(path);
      setEditorContent(res.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao abrir arquivo");
    }
  };

  const saveFile = async () => {
    if (!editorPath) return;
    setError("");
    try {
      if (admin) await api.adminSaveWebSiteFile(site.id, editorPath, editorContent);
      else await api.saveWebSiteFile(site.id, editorPath, editorContent);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar");
    }
  };

  const createFolder = async () => {
    const name = window.prompt("Nome da nova pasta");
    if (!name?.trim()) return;
    setError("");
    setUploadNotice("");
    try {
      if (admin) await api.adminCreateWebSiteFolder(site.id, currentPath, name.trim());
      else await api.createWebSiteFolder(site.id, currentPath, name.trim());
      await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível criar a pasta");
    }
  };

  const uploadEntries = async (entries: FileUploadEntry[]) => {
    if (!entries.length) return;
    setError("");
    setUploadNotice("");
    setActionLoading("upload");
    let ok = 0;
    const failures: string[] = [];
    for (const entry of entries) {
      const label = uploadDisplayName(entry);
      try {
        if (admin) {
          await api.adminUploadWebSiteFile(site.id, currentPath, entry.file, entry.relativePath);
        } else {
          await api.uploadWebSiteFile(site.id, currentPath, entry.file, entry.relativePath);
        }
        ok += 1;
      } catch (e) {
        failures.push(`${label}: ${e instanceof Error ? e.message : "erro"}`);
      }
    }
    await loadFiles();
    setActionLoading(null);
    if (ok) {
      setUploadNotice(
        ok === 1 ? "1 arquivo enviado." : `${ok} arquivos enviados.`
      );
    }
    if (failures.length) {
      setError(
        failures.length === 1
          ? failures[0]
          : `${failures.length} envios falharam. ${failures[0]}`
      );
    }
  };

  const deleteFile = async (entry: GameFileEntry) => {
    const label = entry.is_dir ? `a pasta "${entry.name}"` : `o arquivo "${entry.name}"`;
    if (!window.confirm(`Apagar ${label}? Esta ação não pode ser desfeita.`)) return;
    setError("");
    setUploadNotice("");
    setActionLoading(`delete:${entry.path}`);
    try {
      if (admin) await api.adminDeleteWebSiteFile(site.id, entry.path);
      else await api.deleteWebSiteFile(site.id, entry.path);
      if (editorPath === entry.path || editorPath?.startsWith(`${entry.path}/`)) {
        setEditorPath(null);
        setEditorContent("");
      }
      await loadFiles();
      setUploadNotice(entry.is_dir ? "Pasta apagada." : "Arquivo apagado.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível apagar");
    } finally {
      setActionLoading(null);
    }
  };

  const tabBtn = (id: typeof tab, label: string) => (
    <button
      type="button"
      onClick={() => setTab(id)}
      className={tab === id ? "btn-primary !py-2" : "btn-ghost !py-2"}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {tabBtn("overview", "Visão geral")}
        {!site.php_enabled ? tabBtn("builder", "Criador de página") : null}
        {!site.php_enabled ? tabBtn("stats", "Estatísticas") : null}
        {tabBtn("files", "Arquivos")}
        {tabBtn("logs", "Logs")}
        {site.billing ? tabBtn("billing", "Plano & pagamento") : null}
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-400">
          {error}
        </div>
      )}

      {uploadNotice && (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-400">
          {uploadNotice}
        </div>
      )}

      {tab === "builder" && !site.php_enabled ? (
        <WebPageBuilderPanel site={site} admin={admin} />
      ) : null}

      {tab === "stats" && !site.php_enabled ? (
        <WebSiteAnalyticsPanel site={site} admin={admin} />
      ) : null}

      {tab === "billing" && site.billing ? (
        <WebSiteRenewalPanel site={site} onUpdated={onRefresh} embedded />
      ) : null}

      {tab === "overview" && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="glass-card p-6 space-y-4">
            <h3 className="font-semibold">Publicação</h3>
            <p className="text-sm text-[var(--text-secondary)]">
              Seu site já está online com link personalizado. Prefere usar seu próprio domínio? Configure abaixo em
              poucos cliques.
            </p>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Nome</dt>
                <dd className="font-mono">{site.site_slug}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">URL</dt>
                <dd>
                  <a href={site.public_url} className="text-[var(--accent)]" target="_blank" rel="noreferrer">
                    {site.public_url}
                  </a>
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">RAM</dt>
                <dd>{site.ram_mb} MB</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Disco</dt>
                <dd>{site.disk_mb} MB</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">PHP</dt>
                <dd>{site.php_enabled ? "Sim" : "Não (HTML/CSS/JS)"}</dd>
              </div>
            </dl>
            <label className="block text-sm">
              <span className="text-muted">Domínio próprio (opcional)</span>
              <input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="loja.seudominio.com.br"
                className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
              />
              <WebDomainDnsHint dnsTarget={site.dns_target} compact />
              {site.domain && !site.ssl_active && (
                <div className="mt-2 space-y-2">
                  <p className="text-xs text-amber-400/90 leading-relaxed">
                    HTTPS ainda não está válido para{" "}
                    <strong className="text-[var(--text-secondary)]">{site.domain}</strong>. Confira se o DNS aponta
                    para <strong className="font-mono">{site.dns_target}</strong>. No Cloudflare, use{" "}
                    <strong>Somente DNS</strong> (nuvem cinza) até o certificado ser emitido; depois pode reativar o
                    proxy.
                  </p>
                  <button
                    type="button"
                    disabled={!!actionLoading}
                    onClick={async () => {
                      setActionLoading("ssl");
                      setError("");
                      try {
                        await api.refreshWebSiteSsl(site.id);
                        onRefresh();
                      } catch (e) {
                        setError(e instanceof Error ? e.message : "Erro ao emitir SSL");
                      } finally {
                        setActionLoading(null);
                      }
                    }}
                    className="btn-ghost !py-1.5 text-xs"
                  >
                    {actionLoading === "ssl" ? "Emitindo certificado…" : "Tentar emitir HTTPS agora"}
                  </button>
                </div>
              )}
              {site.domain && site.ssl_active && (
                <p className="mt-2 text-xs text-muted leading-relaxed">
                  HTTPS ativo em <strong className="text-[var(--text-secondary)]">{site.domain}</strong>.
                </p>
              )}
            </label>
            <button
              type="button"
              disabled={!!actionLoading || domain.trim() === (site.domain ?? "")}
              onClick={() => void saveDomain()}
              className="btn-ghost !py-2"
            >
              {actionLoading === "domain" ? "Salvando..." : "Atualizar domínio"}
            </button>
          </div>

          <div className="glass-card p-6 space-y-4">
            <h3 className="font-semibold">Controle</h3>
            <p className="text-sm text-[var(--text-secondary)]">
              Status: <strong>{site.status}</strong>
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!!actionLoading || site.status === "running"}
                onClick={() => void runAction("start")}
                className="btn-primary !py-2"
              >
                {actionLoading === "start" ? "Iniciando..." : "Iniciar"}
              </button>
              <button
                type="button"
                disabled={!!actionLoading || site.status === "stopped"}
                onClick={() => void runAction("stop")}
                className="btn-ghost !py-2"
              >
                {actionLoading === "stop" ? "Parando..." : "Parar"}
              </button>
              <button
                type="button"
                disabled={!!actionLoading}
                onClick={() => void runAction("restart")}
                className="btn-ghost !py-2"
              >
                <SvgRefresh className="w-4 h-4" />
                {actionLoading === "restart" ? "Reiniciando..." : "Reiniciar"}
              </button>
            </div>
            {site.billing && (
              <p className="text-xs text-muted">
                Plano: {formatPrice(site.billing.monthly_cents)}/mês · vence{" "}
                {new Date(site.billing.paid_until).toLocaleDateString("pt-BR")}
                {site.billing.suspended_for_billing ? " · suspenso" : ""}
              </p>
            )}
          </div>
        </div>
      )}

      {tab === "files" && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="glass-card p-4">
            <div className="mb-4 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]/50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="font-medium">Espaço em disco</span>
                <span className="tabular-nums">
                  {formatBytes(usedBytes)}{" "}
                  <span className="text-muted font-normal">de {formatBytes(quotaBytes)}</span>
                </span>
              </div>
              <div className="mt-2 h-2 rounded-full bg-[var(--glass-bg)] overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    quotaPercent >= 90 ? "bg-[var(--danger)]" : "bg-[var(--accent)]"
                  }`}
                  style={{ width: `${quotaPercent}%` }}
                />
              </div>
              <p className="text-xs text-muted mt-1.5">{quotaPercent}% utilizado</p>
            </div>

            <div className="flex flex-wrap items-center gap-1 mb-3 text-sm">
              <button
                type="button"
                className="btn-ghost !py-1 !px-2 text-xs"
                onClick={() => setCurrentPath("")}
              >
                public
              </button>
              {pathParts.map((part, index) => (
                <span key={`${part}-${index}`} className="flex items-center gap-1">
                  <span className="text-muted">/</span>
                  <button
                    type="button"
                    className="btn-ghost !py-1 !px-2 text-xs font-mono"
                    onClick={() => goToPath(index)}
                  >
                    {part}
                  </button>
                </span>
              ))}
            </div>

            <ul className="space-y-1 max-h-80 overflow-y-auto">
              {currentPath && (
                <li>
                  <button
                    type="button"
                    onClick={() => goToPath(pathParts.length - 2)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--glass-bg)] text-left text-sm text-muted"
                  >
                    <SvgFolder className="w-4 h-4" />
                    <span>..</span>
                  </button>
                </li>
              )}
              {files.map((f) => (
                <li key={f.path}>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => (f.is_dir ? setCurrentPath(f.path) : void openFile(f.path))}
                      className="flex-1 flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--glass-bg)] text-left text-sm min-w-0"
                    >
                      {f.is_dir ? (
                        <SvgFolder className="w-4 h-4 text-[var(--accent)] shrink-0" />
                      ) : (
                        <SvgDocument className="w-4 h-4 shrink-0" />
                      )}
                      <span className="truncate">{f.name}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteFile(f)}
                      disabled={actionLoading === `delete:${f.path}`}
                      className="shrink-0 p-1.5 rounded-lg text-[var(--text-muted)] hover:text-red-400 hover:bg-[var(--glass-bg)] disabled:opacity-50"
                      title={f.is_dir ? "Apagar pasta" : "Apagar arquivo"}
                      aria-label={f.is_dir ? `Apagar pasta ${f.name}` : `Apagar arquivo ${f.name}`}
                    >
                      <SvgTrash className="w-4 h-4" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>

            <div className="flex flex-wrap gap-2 mt-3">
              <button type="button" onClick={() => void createFolder()} className="btn-ghost !py-1 text-xs">
                <SvgFolder className="w-3 h-3" /> Nova pasta
              </button>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={actionLoading === "upload"}
                className="btn-ghost !py-1 text-xs"
              >
                <SvgUpload className="w-3 h-3" />
                {actionLoading === "upload" ? "Enviando..." : "Enviar arquivos"}
              </button>
              <button
                type="button"
                onClick={() => folderInputRef.current?.click()}
                disabled={actionLoading === "upload"}
                className="btn-ghost !py-1 text-xs"
              >
                <SvgFolder className="w-3 h-3" /> Enviar pasta
              </button>
              <button type="button" onClick={() => void loadFiles()} className="btn-ghost !py-1 text-xs">
                <SvgRefresh className="w-3 h-3" /> Atualizar
              </button>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) void uploadEntries(collectFilesFromFileList(e.target.files));
                e.target.value = "";
              }}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) void uploadEntries(collectFilesFromFileList(e.target.files));
                e.target.value = "";
              }}
              {...({ webkitdirectory: "", directory: "" } as React.InputHTMLAttributes<HTMLInputElement>)}
            />

            <p className="text-xs text-muted mt-3">
              Você pode criar pastas, enviar vários arquivos de uma vez, enviar uma pasta inteira ou apagar
              arquivos e pastas.
            </p>
          </div>

          <div className="glass-card p-4">
            {editorPath ? (
              <>
                <p className="text-xs font-mono text-muted mb-2 truncate">{editorPath}</p>
                <textarea
                  value={editorContent}
                  onChange={(e) => setEditorContent(e.target.value)}
                  className="w-full h-64 font-mono text-xs p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--glass-border)]"
                  spellCheck={false}
                />
                <button type="button" onClick={() => void saveFile()} className="btn-primary !py-2 mt-3">
                  Salvar arquivo
                </button>
              </>
            ) : (
              <p className="text-sm text-muted py-8 text-center">
                Selecione um arquivo da pasta public/ para editar
              </p>
            )}
          </div>
        </div>
      )}

      {tab === "logs" && (
        <div className="glass-card p-4">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold text-sm">Log do site</h3>
            <button type="button" onClick={() => void loadLogs()} className="btn-ghost !py-1 text-xs">
              <SvgRefresh className="w-3 h-3" /> Atualizar
            </button>
          </div>
          <pre className="text-xs font-mono bg-[var(--bg-elevated)] p-4 rounded-xl max-h-96 overflow-auto whitespace-pre-wrap">
            {logs}
          </pre>
        </div>
      )}
    </div>
  );
}
