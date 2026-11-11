"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import {
  SvgDocument,
  SvgDownload,
  SvgFolder,
  SvgHome,
  SvgPlus,
  SvgRefresh,
  SvgTrash,
  SvgUpload,
} from "@/components/ui/svgs";
import { BusyLabel, InlineLoader } from "@/components/PageLoader";
import {
  api,
  buildHostShellWsUrl,
  type HostFileEntry,
} from "@/lib/api";
import { saveFileAfterDownload } from "@/lib/saveFile";

function formatBytes(n: number | null): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function crumbs(path: string): Array<{ label: string; path: string }> {
  if (!path) return [];
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  const items: Array<{ label: string; path: string }> = [];
  let acc = path.startsWith("/") ? "" : "";
  const isAbs = path.startsWith("/");
  for (const part of parts) {
    acc = isAbs ? `${acc}/${part}` : acc ? `${acc}/${part}` : part;
    items.push({ label: part, path: acc });
  }
  return items;
}

function HostShell() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<"idle" | "connecting" | "open" | "closed">("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || hostRef.current) return;
    const host = document.createElement("div");
    host.style.width = "100%";
    host.style.height = "100%";
    wrap.appendChild(host);
    hostRef.current = host;
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
      termRef.current?.dispose();
      termRef.current = null;
      host.remove();
      hostRef.current = null;
    };
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("closed");
  }, []);

  const connect = async () => {
    setError("");
    setStatus("connecting");
    try {
      const ticket = await api.adminHostShellTicket();
      if (!ticket.available || !ticket.ticket) {
        setError(ticket.message || "Shell indisponível neste servidor");
        setStatus("idle");
        return;
      }
      const url = buildHostShellWsUrl(ticket.ticket);
      const host = hostRef.current;
      if (!url || !host) {
        setError("Não foi possível abrir o WebSocket");
        setStatus("idle");
        return;
      }
      wsRef.current?.close();
      termRef.current?.dispose();
      const term = new Terminal({
        cursorBlink: true,
        convertEol: true,
        fontSize: 13,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        theme: { background: "#0b1220", foreground: "#e2e8f0" },
      });
      const fit = new FitAddon();
      term.loadAddon(fit);
      host.replaceChildren();
      term.open(host);
      fit.fit();
      term.focus();
      termRef.current = term;
      fitRef.current = fit;

      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      const encoder = new TextEncoder();
      const decoder = new TextDecoder("utf-8", { fatal: false });
      const sendSize = () => {
        try {
          fit.fit();
        } catch {
          /* ignore */
        }
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
        }
      };
      ws.onopen = () => {
        setStatus("open");
        sendSize();
        term.focus();
      };
      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          term.write(decoder.decode(new Uint8Array(event.data), { stream: true }));
        } else if (typeof event.data === "string") {
          term.write(event.data);
        }
      };
      ws.onclose = (event) => {
        setStatus("closed");
        window.removeEventListener("resize", sendSize);
        if (event.code && event.code !== 1000) {
          term.write(`\r\n[desconectado ${event.code}]\r\n`);
        } else {
          term.write("\r\n[desconectado]\r\n");
        }
      };
      ws.onerror = () => setError("Falha na conexão SSH");
      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(encoder.encode(data));
      });
      window.addEventListener("resize", sendSize);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao conectar");
      setStatus("idle");
    }
  };

  return (
    <div className="glass-card p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-semibold">SSH do servidor</h3>
          <p className="text-xs text-muted">
            Clique no terminal antes de digitar. A sessão permanece enquanto esta aba estiver aberta.
          </p>
        </div>
        <div className="flex gap-2">
          {status === "open" ? (
            <button type="button" className="btn-ghost !py-2 text-sm" onClick={disconnect}>
              Desconectar
            </button>
          ) : (
            <button type="button" className="btn-primary !py-2 text-sm" onClick={connect} disabled={status === "connecting"}>
              {status === "connecting" ? <BusyLabel>Conectando…</BusyLabel> : "Conectar SSH"}
            </button>
          )}
        </div>
      </div>
      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
      <div
        ref={wrapRef}
        className="h-[380px] rounded-xl overflow-hidden bg-[#0b1220] border border-[var(--glass-border)] p-2"
        onClick={() => termRef.current?.focus()}
      />
    </div>
  );
}

export function AdminHostPanel() {
  const [roots, setRoots] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<HostFileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editorPath, setEditorPath] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async (next = path) => {
    setLoading(true);
    setError("");
    try {
      const listing = await api.adminHostFiles(next);
      setPath(listing.path);
      setParent(listing.parent);
      setEntries(listing.entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao listar");
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    api
      .adminHostInfo()
      .then((info) => {
        setRoots(info.roots);
        return load(info.roots[0] || "");
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Erro ao carregar o host");
        setLoading(false);
      });
    // Primeira carga: info + pasta inicial.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openEntry = async (entry: HostFileEntry) => {
    if (entry.is_dir) {
      setEditorPath(null);
      await load(entry.path);
      return;
    }
    setError("");
    try {
      const file = await api.adminHostFileContent(entry.path);
      setEditorPath(file.path);
      setEditorContent(file.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível abrir");
    }
  };

  const save = async () => {
    if (!editorPath) return;
    setSaving(true);
    setError("");
    try {
      await api.adminHostFileWrite(editorPath, editorContent);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  };

  const runNamed = async (kind: "mkdir" | "file") => {
    if (!path) {
      setError("Abra uma pasta raiz primeiro");
      return;
    }
    const name = window.prompt(kind === "mkdir" ? "Nome da pasta" : "Nome do arquivo");
    if (!name) return;
    setBusy(kind);
    setError("");
    try {
      if (kind === "mkdir") await api.adminHostMkdir(path, name);
      else await api.adminHostCreateFile(path, name);
      await load(path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro");
    } finally {
      setBusy("");
    }
  };

  const rename = async (entry: HostFileEntry) => {
    const name = window.prompt("Novo nome", entry.name);
    if (!name || name === entry.name) return;
    setError("");
    try {
      await api.adminHostRename(entry.path, name);
      if (editorPath === entry.path) setEditorPath(null);
      await load(path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao renomear");
    }
  };

  const remove = async (entry: HostFileEntry) => {
    if (!window.confirm(`Apagar ${entry.name}?`)) return;
    setError("");
    try {
      await api.adminHostDelete(entry.path);
      if (editorPath === entry.path) setEditorPath(null);
      await load(path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao apagar");
    }
  };

  const download = async (entry: HostFileEntry) => {
    try {
      const blob = await api.adminHostDownload(entry.path);
      await saveFileAfterDownload(blob, entry.name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro no download");
    }
  };

  const upload = async (file: File) => {
    if (!path) {
      setError("Abra uma pasta raiz primeiro");
      return;
    }
    setBusy("upload");
    setError("");
    try {
      await api.adminHostUpload(path, file);
      await load(path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro no envio");
    } finally {
      setBusy("");
    }
  };

  const trail = crumbs(path);
  const sensitive = editorPath?.includes(".env");

  return (
    <div className="space-y-6">
      <div className="glass-card p-6">
        <h2 className="font-semibold mb-1">Arquivos do servidor Linux</h2>
        <p className="text-sm text-secondary mb-4">
          Pastas do painel e do site. Alterações valem no disco imediatamente.
        </p>
        <div className="flex flex-wrap gap-2 mb-4">
          {roots.map((root) => (
            <button
              key={root}
              type="button"
              onClick={() => load(root)}
              className={`text-xs px-3 py-1.5 rounded-lg font-mono ${
                path === root || path.startsWith(`${root}/`)
                  ? "btn-primary !py-1.5"
                  : "btn-ghost !py-1.5"
              }`}
            >
              {root}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs mb-4">
          <button type="button" className="btn-ghost !py-1 !px-2" onClick={() => load("")} title="Raízes">
            <SvgHome className="w-4 h-4" />
          </button>
          {parent !== null && parent !== undefined && path && (
            <button type="button" className="btn-ghost !py-1 !px-2" onClick={() => load(parent || "")}>
              ..
            </button>
          )}
          {trail.map((crumb) => (
            <button
              key={crumb.path}
              type="button"
              className="text-muted hover:text-[var(--accent)] font-mono"
              onClick={() => load(crumb.path)}
            >
              /{crumb.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 mb-4">
          <button type="button" className="btn-ghost !py-1.5 text-xs" onClick={() => load(path)} disabled={loading}>
            <SvgRefresh className="w-3.5 h-3.5" /> Atualizar
          </button>
          <button type="button" className="btn-ghost !py-1.5 text-xs" onClick={() => runNamed("mkdir")} disabled={!path}>
            <SvgFolder className="w-3.5 h-3.5" /> Nova pasta
          </button>
          <button type="button" className="btn-ghost !py-1.5 text-xs" onClick={() => runNamed("file")} disabled={!path}>
            <SvgPlus className="w-3.5 h-3.5" /> Novo arquivo
          </button>
          <button
            type="button"
            className="btn-ghost !py-1.5 text-xs"
            onClick={() => fileInputRef.current?.click()}
            disabled={!path || busy === "upload"}
          >
            <SvgUpload className="w-3.5 h-3.5" /> {busy === "upload" ? "Enviando…" : "Enviar"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void upload(file);
            }}
          />
        </div>
        {error && (
          <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-2 mb-3">{error}</p>
        )}
        <div className="overflow-x-auto max-h-[420px]">
          {loading ? (
            <InlineLoader label="Listando…" />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted border-b border-[var(--glass-border)]">
                  <th className="pb-2">Nome</th>
                  <th className="pb-2 w-28">Tamanho</th>
                  <th className="pb-2 w-40">Ações</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.path} className="border-b border-[var(--glass-border)]/40">
                    <td className="py-2 pr-3">
                      <button
                        type="button"
                        className="flex items-center gap-2 text-left hover:text-[var(--accent)]"
                        onClick={() => openEntry(entry)}
                      >
                        {entry.is_dir ? (
                          <SvgFolder className="w-4 h-4 text-[var(--accent)] shrink-0" />
                        ) : (
                          <SvgDocument className="w-4 h-4 shrink-0" />
                        )}
                        <span className="font-mono text-xs truncate">{entry.name}</span>
                      </button>
                    </td>
                    <td className="py-2 text-muted text-xs">{formatBytes(entry.size)}</td>
                    <td className="py-2">
                      <div className="flex gap-1">
                        {!entry.is_dir && (
                          <button type="button" className="btn-ghost !py-1 !px-2 text-xs" onClick={() => download(entry)}>
                            <SvgDownload className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button type="button" className="btn-ghost !py-1 !px-2 text-xs" onClick={() => rename(entry)}>
                          Renomear
                        </button>
                        <button
                          type="button"
                          className="btn-ghost !py-1 !px-2 text-xs text-[var(--danger)]"
                          onClick={() => remove(entry)}
                        >
                          <SvgTrash className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={3} className="py-8 text-center text-muted text-sm">
                      Pasta vazia
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="glass-card p-4">
        {editorPath ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <p className="text-xs font-mono text-muted truncate">{editorPath}</p>
              <button type="button" className="btn-primary !py-1.5 text-sm" onClick={save} disabled={saving}>
                {saving ? "Salvando…" : "Salvar"}
              </button>
            </div>
            {sensitive && (
              <p className="text-xs text-[var(--warning)] mb-2">
                Arquivo sensível. Não compartilhe o conteúdo. Salvar aplica no servidor na hora.
              </p>
            )}
            <textarea
              value={editorContent}
              onChange={(e) => setEditorContent(e.target.value)}
              spellCheck={false}
              className="w-full h-72 font-mono text-xs p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--glass-border)]"
            />
          </>
        ) : (
          <p className="text-sm text-muted py-6 text-center">Abra um arquivo de texto para editar.</p>
        )}
      </div>

      <HostShell />
    </div>
  );
}
