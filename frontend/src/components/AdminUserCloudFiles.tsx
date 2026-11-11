"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type CloudFileItem } from "@/lib/api";
import { saveFileAfterDownload } from "@/lib/saveFile";
import { BusyLabel, InlineLoader } from "@/components/PageLoader";
import { SvgDocument, SvgDownload, SvgFolder } from "@/components/ui/svgs";

type TrailItem = { id: number; name: string };

function formatBytes(n: number) {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

type Props = {
  userId: number;
  onError: (msg: string) => void;
};

export function AdminUserCloudFiles({ userId, onError }: Props) {
  const [trail, setTrail] = useState<TrailItem[]>([]);
  const [items, setItems] = useState<CloudFileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloadId, setDownloadId] = useState<number | null>(null);

  const parentId = trail.length ? trail[trail.length - 1].id : null;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api.adminUserFiles(userId, parentId);
      setItems(rows);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Erro ao listar arquivos CyberCloud");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [userId, parentId, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  const openFolder = (item: CloudFileItem) => {
    setTrail((current) => [...current, { id: item.id, name: item.name }]);
  };

  const goTo = (index: number) => {
    setTrail((current) => current.slice(0, index + 1));
  };

  const downloadFile = async (item: CloudFileItem) => {
    if (item.is_folder || item.upload_status !== "ready") return;
    setDownloadId(item.id);
    onError("");
    try {
      const blob = await api.adminUserFileDownload(userId, item.id);
      await saveFileAfterDownload(blob, item.name, item.mime_type);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Erro ao baixar arquivo");
    } finally {
      setDownloadId(null);
    }
  };

  return (
    <div className="space-y-3">
      <nav className="flex flex-wrap items-center gap-1 text-xs">
        <button
          type="button"
          onClick={() => setTrail([])}
          className="text-[var(--accent)] hover:underline"
        >
          Raiz
        </button>
        {trail.map((folder, index) => (
          <span key={folder.id} className="flex items-center gap-1">
            <span className="text-muted">/</span>
            <button
              type="button"
              onClick={() => goTo(index)}
              className="text-[var(--accent)] hover:underline truncate max-w-[140px]"
            >
              {folder.name}
            </button>
          </span>
        ))}
      </nav>
      {loading ? (
        <InlineLoader label="Carregando arquivos…" />
      ) : items.length === 0 ? (
        <p className="text-secondary text-sm">Nenhum arquivo nesta pasta.</p>
      ) : (
        <div className="space-y-1 max-h-[280px] overflow-y-auto">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-[var(--bg-elevated)]"
            >
              {item.is_folder ? (
                <button
                  type="button"
                  onClick={() => openFolder(item)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <SvgFolder className="w-4 h-4 shrink-0 text-amber-400" />
                  <span className="truncate text-sm">{item.name}</span>
                </button>
              ) : (
                <>
                  <SvgDocument className="w-4 h-4 shrink-0 text-secondary" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{item.name}</p>
                    <p className="text-xs text-muted">
                      {item.upload_status === "ready"
                        ? formatBytes(item.size_bytes)
                        : "Envio incompleto"}
                    </p>
                  </div>
                  {item.upload_status === "ready" && (
                    <button
                      type="button"
                      disabled={downloadId === item.id}
                      onClick={() => void downloadFile(item)}
                      className="btn-ghost !py-1 !px-2 text-xs shrink-0"
                      title="Baixar"
                    >
                      {downloadId === item.id ? (
                        <BusyLabel>Baixando…</BusyLabel>
                      ) : (
                        <SvgDownload className="w-4 h-4" />
                      )}
                    </button>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
