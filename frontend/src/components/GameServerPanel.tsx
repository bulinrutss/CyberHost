"use client";

import { useCallback, useEffect, useState } from "react";
import { SvgDocument, SvgFolder, SvgRefresh } from "@/components/ui/svgs";
import { api, type GameFileEntry, type GameServer } from "@/lib/api";
import { formatBRL } from "@/lib/gameProvisionLabels";

type Props = {
  server: GameServer;
  onRefresh: () => void;
};

export function GameServerPanel({ server, onRefresh }: Props) {
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [files, setFiles] = useState<GameFileEntry[]>([]);
  const [currentPath, setCurrentPath] = useState("");
  const [editorPath, setEditorPath] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"overview" | "files" | "logs">("overview");

  const loadLogs = useCallback(async () => {
    const res = await api.gameServerLogs(server.id, 150);
    setLogs(res.lines || "(sem logs ainda)");
  }, [server.id]);

  const loadFiles = useCallback(async () => {
    const list = await api.gameServerFiles(server.id, currentPath);
    setFiles(list);
  }, [server.id, currentPath]);

  useEffect(() => {
    if (tab === "logs") loadLogs();
  }, [tab, loadLogs]);

  useEffect(() => {
    if (tab === "files") loadFiles();
  }, [tab, loadFiles, currentPath]);

  const runAction = async (action: "start" | "stop" | "restart") => {
    setActionLoading(action);
    setError("");
    try {
      if (action === "start") await api.startGameServer(server.id);
      else if (action === "stop") await api.stopGameServer(server.id);
      else await api.restartGameServer(server.id);
      onRefresh();
      if (tab === "logs") await loadLogs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro na ação");
    } finally {
      setActionLoading(null);
    }
  };

  const openFile = async (path: string) => {
    setError("");
    try {
      const res = await api.gameServerFileContent(server.id, path);
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
      await api.saveGameServerFile(server.id, editorPath, editorContent);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar");
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
        {tabBtn("files", "Arquivos")}
        {tabBtn("logs", "Logs")}
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-400">
          {error}
        </div>
      )}

      {tab === "overview" && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="glass-card p-6 space-y-4">
            <h3 className="font-semibold">Conexão</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Endereço</dt>
                <dd className="font-mono">{server.address}</dd>
              </div>
              {server.query_port && (
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">Query</dt>
                  <dd className="font-mono">
                    {server.public_ip}:{server.query_port}
                  </dd>
                </div>
              )}
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Slots</dt>
                <dd>{server.slots}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">RAM</dt>
                <dd>{server.ram_mb / 1024} GB</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Config</dt>
                <dd className="font-mono text-xs">{server.config_file}</dd>
              </div>
            </dl>
          </div>

          <div className="glass-card p-6 space-y-4">
            <h3 className="font-semibold">Controle</h3>
            <p className="text-sm text-[var(--text-secondary)]">
              Status: <strong>{server.status}</strong>
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!!actionLoading || server.status === "running"}
                onClick={() => runAction("start")}
                className="btn-primary !py-2"
              >
                {actionLoading === "start" ? "Iniciando..." : "Iniciar"}
              </button>
              <button
                type="button"
                disabled={!!actionLoading || server.status === "stopped"}
                onClick={() => runAction("stop")}
                className="btn-ghost !py-2"
              >
                {actionLoading === "stop" ? "Parando..." : "Parar"}
              </button>
              <button
                type="button"
                disabled={!!actionLoading}
                onClick={() => runAction("restart")}
                className="btn-ghost !py-2"
              >
                <SvgRefresh className="w-4 h-4" />
                {actionLoading === "restart" ? "Reiniciando..." : "Reiniciar"}
              </button>
            </div>
            {server.billing && (
              <p className="text-xs text-muted">
                Plano: {formatBRL(server.billing.monthly_cents)}/mês · vence{" "}
                {new Date(server.billing.paid_until).toLocaleDateString("pt-BR")}
              </p>
            )}
          </div>
        </div>
      )}

      {tab === "files" && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="glass-card p-4">
            <div className="flex items-center gap-2 mb-3 text-sm">
              <button
                type="button"
                className="btn-ghost !py-1 !px-2 text-xs"
                onClick={() => setCurrentPath("")}
              >
                /
              </button>
              {currentPath && (
                <span className="text-muted font-mono text-xs truncate">{currentPath}</span>
              )}
            </div>
            <ul className="space-y-1 max-h-80 overflow-y-auto">
              {files.map((f) => (
                <li key={f.path}>
                  <button
                    type="button"
                    onClick={() => (f.is_dir ? setCurrentPath(f.path) : openFile(f.path))}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--glass-bg)] text-left text-sm"
                  >
                    {f.is_dir ? (
                      <SvgFolder className="w-4 h-4 text-[var(--accent)]" />
                    ) : (
                      <SvgDocument className="w-4 h-4" />
                    )}
                    <span className="truncate">{f.name}</span>
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" onClick={loadFiles} className="btn-ghost !py-1 mt-3 text-xs w-full">
              <SvgRefresh className="w-3 h-3" /> Atualizar lista
            </button>
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
                <button type="button" onClick={saveFile} className="btn-primary !py-2 mt-3">
                  Salvar arquivo
                </button>
              </>
            ) : (
              <p className="text-sm text-muted py-8 text-center">
                Selecione um arquivo para editar (ex.: {server.config_file})
              </p>
            )}
          </div>
        </div>
      )}

      {tab === "logs" && (
        <div className="glass-card p-4">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold text-sm">Console do servidor</h3>
            <button type="button" onClick={loadLogs} className="btn-ghost !py-1 text-xs">
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
