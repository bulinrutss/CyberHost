"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  SvgDocument,
  SvgDownload,
  SvgEye,
  SvgFolder,
  SvgHome,
  SvgPlus,
  SvgRefresh,
  SvgTrash,
  SvgUpload,
  SvgChevronDown,
} from "@/components/ui/svgs";
import { PageLoader, InlineLoader, BusyLabel } from "@/components/PageLoader";
import {
  bytesFromChunkProgress,
  chunkCount,
  collectFilesFromDataTransfer,
  collectFilesFromFileList,
  computePipelineProgress,
  DEFAULT_CHUNK_SIZE_BYTES,
  estimateRemainingSeconds,
  fileRelativePath,
  formatBytes,
  formatDate,
  formatDuration,
  formatSpeed,
  MAX_CONCURRENT_UPLOADS,
  MAX_UPLOAD_BYTES,
  resolveMaxUploadBytes,
  envMaxUploadBytes,
  parseRelativePath,
  readFileChunk,
  smoothSpeed,
  uploadDisplayName,
  uploadEntryKey,
  uploadPhaseLabel,
  canPreviewTextFile,
  isTextFile,
  textPreviewLimitLabel,
  type FileUploadEntry,
  type UploadPipelinePhase,
  type UploadTask,
} from "@/lib/cloudFiles";
import { PixPayButton, PixPaymentModal } from "@/components/PixPaymentModal";
import {
  api,
  formatPrice,
  getToken,
  type CloudFileItem,
  type CloudQuota,
  type CloudStoragePackage,
  type CloudUploadProgress,
} from "@/lib/api";
import { cloudError, cloudLog, cloudWarn } from "@/lib/cloudLog";
import { API_URL } from "@/lib/apiBase";
import { saveFileAfterDownload } from "@/lib/saveFile";

const STORAGE_PENDING_ORDER_KEY = "cloud_storage_pending_order";

type CloudTab = "files" | "billing";

type Breadcrumb = { id: number | null; name: string };

type UploadJob = {
  file: File;
  relativePath: string | null;
  targetParentId: number | null;
  fileId?: number;
  progress: number;
  phase: UploadPipelinePhase;
  error?: string;
  chunksDone: number;
  totalChunks: number;
  syncDone: number;
  chunkSizeBytes: number;
  startedAt: number;
  speedBps: number;
  lastMetricAt: number;
  lastMetricBytes: number;
};

function patchUploadJob(
  job: UploadJob,
  patch: Partial<UploadJob> & {
    chunksDone?: number;
    syncDone?: number;
    phase?: UploadPipelinePhase;
  }
): UploadJob {
  const next: UploadJob = { ...job, ...patch };
  const now = Date.now();
  const phase = next.phase;
  const chunksDone = next.chunksDone;
  const syncDone = next.syncDone;
  const totalChunks = next.totalChunks;

  const uploadBytes = bytesFromChunkProgress(
    next.file.size,
    chunksDone,
    totalChunks,
    next.chunkSizeBytes
  );
  const syncBytes = bytesFromChunkProgress(
    next.file.size,
    syncDone,
    totalChunks,
    next.chunkSizeBytes
  );
  const processedBytes =
    phase === "syncing" || phase === "finalizing" || phase === "done"
      ? uploadBytes + syncBytes
      : uploadBytes;

  if (processedBytes > next.lastMetricBytes && now > next.lastMetricAt) {
    const dt = (now - next.lastMetricAt) / 1000;
    if (dt >= 0.25) {
      const instant = (processedBytes - next.lastMetricBytes) / dt;
      next.speedBps = smoothSpeed(next.speedBps, instant);
      next.lastMetricAt = now;
      next.lastMetricBytes = processedBytes;
    }
  } else if (next.lastMetricAt === 0) {
    next.lastMetricAt = now;
    next.lastMetricBytes = processedBytes;
  }

  next.progress = computePipelineProgress(chunksDone, syncDone, totalChunks, phase);
  return next;
}

async function runUploadPool<T>(
  items: T[],
  worker: (item: T) => Promise<void>,
  concurrency: number
) {
  let nextIndex = 0;
  async function runWorker() {
    while (nextIndex < items.length) {
      const item = items[nextIndex++];
      await worker(item);
    }
  }
  const workers = Math.min(concurrency, items.length);
  await Promise.all(Array.from({ length: workers }, () => runWorker()));
}

function matchesUploadJob(
  job: UploadJob,
  task: Pick<UploadTask, "file" | "relativePath">
): boolean {
  return uploadEntryKey(job) === uploadEntryKey(task);
}

function formatOversizeNotice(files: File[], maxBytes: number): string {
  const label = formatBytes(maxBytes);
  if (files.length === 1) {
    return `Ignorado (excede ${label}): ${uploadDisplayName({
      file: files[0],
      relativePath: fileRelativePath(files[0]),
    })}`;
  }
  const names = files
    .slice(0, 5)
    .map((f) => uploadDisplayName({ file: f, relativePath: fileRelativePath(f) }))
    .join(", ");
  const extra = files.length > 5 ? ` e mais ${files.length - 5}` : "";
  return `${files.length} arquivo(s) ignorado(s) por exceder ${label}: ${names}${extra}`;
}

function isAbortError(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

function isUploadTerminal(phase: UploadPipelinePhase): boolean {
  return phase === "done" || phase === "error" || phase === "cancelled";
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = window.setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener(
        "abort",
        () => {
          window.clearTimeout(timer);
          reject(new DOMException("Aborted", "AbortError"));
        },
        { once: true }
      );
    }
  });
}

async function uploadChunkWithRetry(
  fileId: number,
  chunkIndex: number,
  blob: Blob,
  signal?: AbortSignal
) {
  cloudLog(`Enviando fragmento ${chunkIndex + 1}`, { fileId, bytes: blob.size });
  for (let attempt = 0; attempt < 4; attempt++) {
    throwIfAborted(signal);
    try {
      await api.cloudUploadChunk(fileId, chunkIndex, blob, signal);
      cloudLog(`Fragmento ${chunkIndex + 1} OK`, { fileId });
      return;
    } catch (e) {
      if (isAbortError(e)) throw e;
      cloudWarn(`Fragmento ${chunkIndex + 1} tentativa ${attempt + 1}/4 falhou`, e);
      if (attempt === 3) throw e;
      await sleep(1000 * (attempt + 1), signal);
    }
  }
}

async function waitForDiscordSync(
  fileId: number,
  total: number,
  onProgress: (synced: number, received: number) => void,
  signal?: AbortSignal
) {
  cloudLog("Iniciando sync Discord", { fileId, total });
  throwIfAborted(signal);

  let syncInFlight: Promise<void> | null = null;

  const startSyncIfNeeded = (received: number, synced: number) => {
    if (synced >= total || received <= synced || syncInFlight) return;
    cloudLog("Disparando sync-pending em background", { fileId, received, synced });
    syncInFlight = api
      .cloudSyncPending(fileId, signal)
      .then(() => {
        cloudLog("sync-pending concluído", { fileId });
      })
      .catch((e) => {
        if (isAbortError(e)) return;
        cloudWarn("sync-pending falhou — nova tentativa no próximo poll", { fileId, erro: e });
      })
      .finally(() => {
        syncInFlight = null;
      });
  };

  for (let i = 0; i < 3600; i++) {
    throwIfAborted(signal);
    const progress = await api.cloudUploadProgress(fileId, signal);
    onProgress(progress.synced_chunks, progress.received_chunks);
    cloudLog(`Poll Discord ${progress.synced_chunks}/${total}`, { fileId, progress });

    if (progress.synced_chunks >= total) {
      if (syncInFlight) await syncInFlight;
      return progress;
    }

    startSyncIfNeeded(progress.received_chunks, progress.synced_chunks);
    await sleep(syncInFlight ? 400 : 800, signal);
  }

  if (syncInFlight) await syncInFlight;
  throw new Error("Timeout aguardando sincronização com Discord");
}

type SortField = "name" | "size" | "chunks" | "updated";
type SortDir = "asc" | "desc";
type TypeFilter = "all" | "folders" | "files" | "incomplete";

function compareItems(a: CloudFileItem, b: CloudFileItem, field: SortField, dir: SortDir): number {
  const mul = dir === "asc" ? 1 : -1;

  if (field === "name") {
    return mul * a.name.localeCompare(b.name, "pt-BR", { sensitivity: "base" });
  }
  if (field === "size") {
    const av = a.is_folder ? -1 : a.size_bytes;
    const bv = b.is_folder ? -1 : b.size_bytes;
    return mul * (av - bv);
  }
  if (field === "chunks") {
    const av = a.is_folder ? -1 : a.chunk_count;
    const bv = b.is_folder ? -1 : b.chunk_count;
    return mul * (av - bv);
  }
  const av = new Date(a.updated_at).getTime();
  const bv = new Date(b.updated_at).getTime();
  return mul * (av - bv);
}

function sortIndicator(active: boolean, dir: SortDir): string {
  if (!active) return "↕";
  return dir === "asc" ? "↑" : "↓";
}

type UploadBatchStats = {
  total: number;
  completed: number;
  failed: number;
  cancelled: number;
  queued: number;
  active: number;
  totalBytes: number;
  processedBytes: number;
  overallProgress: number;
  elapsedSec: number;
  etaSec: number | null;
  avgSpeed: number;
};

function computeUploadBatchStats(jobs: UploadJob[]): UploadBatchStats {
  if (!jobs.length) {
    return {
      total: 0,
      completed: 0,
      failed: 0,
      cancelled: 0,
      queued: 0,
      active: 0,
      totalBytes: 0,
      processedBytes: 0,
      overallProgress: 0,
      elapsedSec: 0,
      etaSec: null,
      avgSpeed: 0,
    };
  }

  let totalBytes = 0;
  let weightedProgress = 0;
  let completed = 0;
  let failed = 0;
  let cancelled = 0;
  let queued = 0;
  let active = 0;
  let speedSum = 0;
  let speedCount = 0;
  let earliestStart = jobs[0].startedAt;

  for (const job of jobs) {
    totalBytes += job.file.size;
    weightedProgress += job.progress * job.file.size;
    earliestStart = Math.min(earliestStart, job.startedAt);

    if (job.phase === "done") completed++;
    else if (job.phase === "error") failed++;
    else if (job.phase === "cancelled") cancelled++;
    else if (job.phase === "pending") queued++;
    else active++;

    if (
      job.speedBps > 0 &&
      !isUploadTerminal(job.phase) &&
      job.phase !== "pending"
    ) {
      speedSum += job.speedBps;
      speedCount++;
    }
  }

  const overallProgress =
    totalBytes > 0 ? Math.min(100, Math.round(weightedProgress / totalBytes)) : 0;
  const elapsedSec = (Date.now() - earliestStart) / 1000;
  const processedBytes = Math.round((totalBytes * overallProgress) / 100);

  return {
    total: jobs.length,
    completed,
    failed,
    cancelled,
    queued,
    active,
    totalBytes,
    processedBytes,
    overallProgress,
    elapsedSec,
    etaSec: estimateRemainingSeconds(elapsedSec, overallProgress),
    avgSpeed: speedCount > 0 ? speedSum / speedCount : 0,
  };
}

function uploadJobKey(job: UploadJob): string {
  return uploadEntryKey(job);
}

type DownloadPhase = "preparing" | "downloading" | "saving" | "done" | "cancelled" | "error";

type DownloadJob = {
  id: number;
  name: string;
  sizeBytes: number;
  mimeType: string | null;
  phase: DownloadPhase;
  progress: number;
  loadedBytes: number;
  totalBytes: number | null;
  startedAt: number;
  error?: string;
};

const UPLOAD_CLOSE_MS = 500;
const UPLOAD_ERROR_CLOSE_MS = 5000;
const DOWNLOAD_CLOSE_MS = 500;
const DOWNLOAD_ERROR_CLOSE_MS = 5000;

export function CloudFilesPanel() {
  const searchParams = useSearchParams();
  const [items, setItems] = useState<CloudFileItem[]>([]);
  const [quota, setQuota] = useState<CloudQuota | null>(null);
  const [storageLimits, setStorageLimits] = useState<{
    max_upload_bytes: number;
    chunk_size_bytes: number;
  } | null>(() => {
    const envLimit = envMaxUploadBytes();
    if (envLimit > 0) {
      return { max_upload_bytes: envLimit, chunk_size_bytes: DEFAULT_CHUNK_SIZE_BYTES };
    }
    return null;
  });
  const [storagePackages, setStoragePackages] = useState<CloudStoragePackage[]>([]);
  const [purchasingSlug, setPurchasingSlug] = useState<string | null>(null);
  const [renewMonths, setRenewMonths] = useState(1);
  const [renewQuote, setRenewQuote] = useState<{
    total_cents: number;
    monthly_cents: number;
    new_paid_until: string;
  } | null>(null);
  const [renewLoading, setRenewLoading] = useState(false);
  const [renewError, setRenewError] = useState("");
  const [pixOpen, setPixOpen] = useState(false);
  const [pixRefreshing, setPixRefreshing] = useState(false);
  const [pendingPix, setPendingPix] = useState<{
    orderId: number;
    brCode: string | null;
    qrBase64: string | null;
    expiresAt: string | null;
    amountCents: number;
  } | null>(null);
  const [activeTab, setActiveTab] = useState<CloudTab>("files");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadNotice, setUploadNotice] = useState("");
  const [parentId, setParentId] = useState<number | null>(null);
  const [breadcrumb, setBreadcrumb] = useState<Breadcrumb[]>([{ id: null, name: "Raiz" }]);
  const [dragOver, setDragOver] = useState(false);
  const [uploads, setUploads] = useState<UploadJob[]>([]);
  const [showFolderModal, setShowFolderModal] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [downloadJob, setDownloadJob] = useState<DownloadJob | null>(null);
  const [downloadTick, setDownloadTick] = useState(0);
  const [textPreview, setTextPreview] = useState<{
    item: CloudFileItem;
    content: string;
    loading: boolean;
    error: string;
  } | null>(null);
  const [itemProgress, setItemProgress] = useState<Record<number, CloudUploadProgress>>({});
  const [uploadTick, setUploadTick] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [moveBrowseParentId, setMoveBrowseParentId] = useState<number | null>(null);
  const [moveBrowseBreadcrumb, setMoveBrowseBreadcrumb] = useState<Breadcrumb[]>([
    { id: null, name: "Raiz" },
  ]);
  const [moveBrowseFolders, setMoveBrowseFolders] = useState<CloudFileItem[]>([]);
  const [moveBrowseLoading, setMoveBrowseLoading] = useState(false);
  const [uploadPanelExpanded, setUploadPanelExpanded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const pollBusyRef = useRef(false);
  const uploadControllersRef = useRef<Map<string, AbortController>>(new Map());
  const downloadAbortRef = useRef<AbortController | null>(null);
  const downloadCancelledRef = useRef(false);
  const loadSeqRef = useRef(0);

  const uploadingIds = useMemo(
    () =>
      items
        .filter((i) => !i.is_folder && i.upload_status === "uploading")
        .map((i) => i.id),
    [items]
  );

  useEffect(() => {
    cloudLog("Painel montado", {
      apiUrl: API_URL || "(same-origin)",
      session: typeof window !== "undefined" && getToken() ? "sim" : "NÃO",
    });
    api.cloudFilesLimits()
      .then((limits) => {
        setStorageLimits((prev) => ({
          max_upload_bytes: resolveMaxUploadBytes(limits.max_upload_bytes, prev?.max_upload_bytes),
          chunk_size_bytes: limits.chunk_size_bytes || prev?.chunk_size_bytes || DEFAULT_CHUNK_SIZE_BYTES,
        }));
        cloudLog("Limites de upload", limits);
      })
      .catch(() => {
        api.paymentConfig().then((cfg) => {
          if (cfg.cloud_max_upload_bytes) {
            setStorageLimits((prev) => ({
              max_upload_bytes: resolveMaxUploadBytes(cfg.cloud_max_upload_bytes, prev?.max_upload_bytes),
              chunk_size_bytes: cfg.cloud_chunk_size_bytes || prev?.chunk_size_bytes || DEFAULT_CHUNK_SIZE_BYTES,
            }));
          }
        }).catch(() => {});
      });
  }, []);

  const load = useCallback(async () => {
    const seq = ++loadSeqRef.current;
    cloudLog("Carregando lista", { parentId });
    try {
      const sync = await api.cloudStorageSyncPending().catch(() => null);
      if (seq !== loadSeqRef.current) return;

      const [files, q, packages, limits, status] = await Promise.all([
        api.cloudList(parentId),
        api.cloudQuota(),
        api.cloudStoragePackages().catch(() => [] as CloudStoragePackage[]),
        api.cloudFilesLimits().catch(() => null),
        api.cloudStorageStatus().catch(() => null),
      ]);
      if (seq !== loadSeqRef.current) return;

      setItems(files);
      setQuota(q);
      setStoragePackages(packages);
      if (limits?.max_upload_bytes) {
        setStorageLimits((prev) => ({
          max_upload_bytes: resolveMaxUploadBytes(limits.max_upload_bytes, prev?.max_upload_bytes),
          chunk_size_bytes: limits.chunk_size_bytes || prev?.chunk_size_bytes || DEFAULT_CHUNK_SIZE_BYTES,
        }));
      } else if (status?.max_upload_bytes) {
        setStorageLimits((prev) => ({
          max_upload_bytes: resolveMaxUploadBytes(status.max_upload_bytes, prev?.max_upload_bytes),
          chunk_size_bytes: status.chunk_size_bytes ?? prev?.chunk_size_bytes ?? DEFAULT_CHUNK_SIZE_BYTES,
        }));
      } else if (q.max_upload_bytes) {
        setStorageLimits((prev) => ({
          max_upload_bytes: resolveMaxUploadBytes(q.max_upload_bytes, prev?.max_upload_bytes),
          chunk_size_bytes: q.chunk_size_bytes ?? prev?.chunk_size_bytes ?? DEFAULT_CHUNK_SIZE_BYTES,
        }));
      }
      setError("");
      cloudLog("Lista carregada", {
        arquivos: files.length,
        quota: q.quota_bytes,
        extra: q.extra_bytes,
        credited: sync?.credited_gb ?? 0,
      });
      if (sync && sync.credited_gb > 0) {
        setUploadNotice(`+${sync.credited_gb} GB adicionados ao seu CyberCloud.`);
      }
    } catch (e) {
      if (seq !== loadSeqRef.current) return;
      cloudError("Erro ao carregar", e);
      setError(e instanceof Error ? e.message : "Erro ao carregar arquivos");
    } finally {
      if (seq === loadSeqRef.current) setLoading(false);
    }
  }, [parentId]);

  useEffect(() => {
    setLoading(true);
    load();
    setSelectedIds(new Set());
  }, [load]);

  useEffect(() => {
    const raw = sessionStorage.getItem(STORAGE_PENDING_ORDER_KEY);
    if (!raw) return;
    const orderId = Number(raw);
    if (!Number.isFinite(orderId)) return;
    let cancelled = false;
    api
      .cloudStorageSyncPayment(orderId)
      .then((sync) => {
        if (cancelled) return;
        if (sync.status === "paid") {
          sessionStorage.removeItem(STORAGE_PENDING_ORDER_KEY);
          void load();
          return;
        }
        setPendingPix({
          orderId,
          brCode: sync.pix_br_code ?? null,
          qrBase64: sync.pix_qr_base64 ?? null,
          expiresAt: sync.pix_expires_at ?? null,
          amountCents: sync.total_cents ?? 0,
        });
        setPixOpen(true);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(() => {
    if (!pendingPix) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const sync = await api.cloudStorageSyncPayment(pendingPix.orderId);
        if (cancelled) return;
        if (sync.status === "paid") {
          sessionStorage.removeItem(STORAGE_PENDING_ORDER_KEY);
          setPendingPix(null);
          setPixOpen(false);
          await load();
          setUploadNotice("Pagamento Pix confirmado.");
          return;
        }
        setPendingPix((prev) =>
          prev
            ? {
                ...prev,
                brCode: sync.pix_br_code ?? prev.brCode,
                qrBase64: sync.pix_qr_base64 ?? prev.qrBase64,
                expiresAt: sync.pix_expires_at ?? prev.expiresAt,
                amountCents: sync.total_cents || prev.amountCents,
              }
            : prev
        );
      } catch {
        /* ainda pendente */
      }
    };
    const interval = window.setInterval(poll, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [pendingPix?.orderId, load]);

  useEffect(() => {
    const storage = searchParams.get("storage");
    const hasOrder = searchParams.get("order") != null;
    const isPaymentReturn =
      storage === "credited" ||
      storage === "renewed" ||
      storage === "paid" ||
      storage === "pending" ||
      hasOrder;
    if (!isPaymentReturn) return;

    sessionStorage.removeItem(STORAGE_PENDING_ORDER_KEY);
    window.history.replaceState({}, "", window.location.pathname);
    setActiveTab("billing");

    let cancelled = false;
    let attempts = 0;

    const pollAfterPayment = async () => {
      if (cancelled) return;
      try {
        const sync = await api.cloudStorageSyncPending();
        await load();
        if (sync.credited_gb > 0) return;
      } catch {
        await load().catch(() => {});
      }
      if (cancelled) return;
      attempts += 1;
      if (attempts >= 12) return;
      window.setTimeout(pollAfterPayment, 2500);
    };

    pollAfterPayment();
    return () => {
      cancelled = true;
    };
  }, [searchParams, load]);

  useEffect(() => {
    const billing = quota?.billing;
    if (!billing || billing.contracted_gb <= 0 || !billing.paid_until) {
      setRenewQuote(null);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const q = await api.cloudStorageRenewQuote(renewMonths);
        setRenewQuote({
          total_cents: q.total_cents,
          monthly_cents: q.monthly_cents,
          new_paid_until: q.new_paid_until,
        });
        setRenewError("");
      } catch (e) {
        setRenewQuote(null);
        setRenewError(e instanceof Error ? e.message : "Erro ao calcular renovação");
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [quota?.billing, renewMonths]);

  useEffect(() => {
    const onFocus = () => {
      void load();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  const loadMoveBrowse = useCallback(async (browseParentId: number | null) => {
    setMoveBrowseLoading(true);
    try {
      const list = await api.cloudList(browseParentId);
      setMoveBrowseFolders(list.filter((i) => i.is_folder));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar pastas");
    } finally {
      setMoveBrowseLoading(false);
    }
  }, []);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "name" ? "asc" : "desc");
    }
  };

  const filteredItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return items.filter((item) => {
      if (q && !item.name.toLowerCase().includes(q)) return false;
      if (typeFilter === "folders" && !item.is_folder) return false;
      if (typeFilter === "files" && item.is_folder) return false;
      if (typeFilter === "incomplete") {
        if (item.is_folder || item.upload_status !== "uploading") return false;
      }
      return true;
    });
  }, [items, searchQuery, typeFilter]);

  const displayItems = useMemo(() => {
    return [...filteredItems].sort((a, b) => {
      if (sortField === "name" && a.is_folder !== b.is_folder) {
        return sortDir === "asc" ? (a.is_folder ? -1 : 1) : a.is_folder ? 1 : -1;
      }
      return compareItems(a, b, sortField, sortDir);
    });
  }, [filteredItems, sortField, sortDir]);

  const visibleIds = useMemo(() => displayItems.map((i) => i.id), [displayItems]);
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
  const someVisibleSelected =
    visibleIds.some((id) => selectedIds.has(id)) && !allVisibleSelected;

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        visibleIds.forEach((id) => next.delete(id));
      } else {
        visibleIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const openMoveModal = () => {
    setMoveBrowseParentId(null);
    setMoveBrowseBreadcrumb([{ id: null, name: "Raiz" }]);
    setShowMoveModal(true);
    void loadMoveBrowse(null);
  };

  const navigateMoveBrowse = (index: number) => {
    const target = moveBrowseBreadcrumb[index];
    setMoveBrowseBreadcrumb(moveBrowseBreadcrumb.slice(0, index + 1));
    setMoveBrowseParentId(target.id);
    void loadMoveBrowse(target.id);
  };

  const enterMoveFolder = (folder: CloudFileItem) => {
    setMoveBrowseBreadcrumb((prev) => [...prev, { id: folder.id, name: folder.name }]);
    setMoveBrowseParentId(folder.id);
    void loadMoveBrowse(folder.id);
  };

  const moveSelected = async () => {
    if (!selectedIds.size) return;
    setBulkBusy(true);
    setError("");
    try {
      const { moved } = await api.cloudMove(Array.from(selectedIds), moveBrowseParentId);
      cloudLog("Itens movidos", { moved, destino: moveBrowseParentId });
      setSelectedIds(new Set());
      setShowMoveModal(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao mover itens");
    } finally {
      setBulkBusy(false);
    }
  };

  const deleteSelected = async () => {
    if (!selectedIds.size) return;
    if (!confirm(`Excluir ${selectedIds.size} item(ns) selecionado(s)?`)) return;
    setBulkBusy(true);
    setError("");
    try {
      for (const id of Array.from(selectedIds)) {
        await api.cloudDelete(id);
      }
      setSelectedIds(new Set());
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao excluir selecionados");
    } finally {
      setBulkBusy(false);
    }
  };

  useEffect(() => {
    if (!uploadingIds.length) return;

    const poll = async () => {
      if (pollBusyRef.current) return;
      pollBusyRef.current = true;
      try {
        for (const id of uploadingIds) {
          const item = items.find((i) => i.id === id);
          if (!item) continue;
          try {
            cloudLog("Poll upload incompleto", { id, nome: item.name });
            const progress = await api.cloudUploadProgress(id);
            setItemProgress((prev) => ({ ...prev, [id]: progress }));
            if (
              progress.received_chunks >= progress.chunk_count &&
              progress.synced_chunks < progress.chunk_count
            ) {
              cloudLog("Poll disparando sync-pending", { id });
              await api.cloudSyncPending(id);
            }
          } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            if (msg.includes("Not Found") || msg.includes("não encontrado")) {
              cloudWarn("Upload órfão — removendo da lista", { id, nome: item.name });
              setItems((prev) => prev.filter((i) => i.id !== id));
              setItemProgress((prev) => {
                const next = { ...prev };
                delete next[id];
                return next;
              });
            } else {
              cloudError("Poll falhou", { id, nome: item.name, erro: e });
            }
          }
        }
      } finally {
        pollBusyRef.current = false;
      }
    };

    poll();
    const interval = setInterval(poll, 4000);
    return () => clearInterval(interval);
  }, [uploadingIds, items]);

  const navigateTo = (index: number) => {
    const target = breadcrumb[index];
    setBreadcrumb(breadcrumb.slice(0, index + 1));
    setParentId(target.id);
    setSelectedIds(new Set());
  };

  const openFolder = (folder: CloudFileItem) => {
    setBreadcrumb((prev) => [...prev, { id: folder.id, name: folder.name }]);
    setParentId(folder.id);
    setSelectedIds(new Set());
  };

  const chunkSizeBytes =
    storageLimits?.chunk_size_bytes ??
    quota?.chunk_size_bytes ??
    DEFAULT_CHUNK_SIZE_BYTES;
  const maxUploadBytes = resolveMaxUploadBytes(
    storageLimits?.max_upload_bytes,
    quota?.max_upload_bytes
  );

  const cleanupUploadOnServer = async (fileId: number | undefined) => {
    if (!fileId) return;
    try {
      await api.cloudDelete(fileId);
      cloudLog("Upload cancelado — removido do servidor", { fileId });
    } catch (e) {
      cloudWarn("Falha ao remover upload cancelado no servidor", { fileId, erro: e });
    }
  };

  const ensureFolder = async (
    name: string,
    folderParentId: number | null,
    cache: Map<string, number>
  ): Promise<number> => {
    const cacheKey = `${folderParentId ?? "root"}/${name}`;
    const cached = cache.get(cacheKey);
    if (cached !== undefined) return cached;

    try {
      const created = await api.cloudCreateFolder({ name, parent_id: folderParentId });
      cache.set(cacheKey, created.id);
      return created.id;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("Já existe") || msg.includes("nome")) {
        const siblings = await api.cloudList(folderParentId);
        const existing = siblings.find((i) => i.is_folder && i.name === name);
        if (existing) {
          cache.set(cacheKey, existing.id);
          return existing.id;
        }
      }
      throw e;
    }
  };

  const buildUploadTasks = async (
    entries: FileUploadEntry[]
  ): Promise<{ tasks: UploadTask[]; oversize: File[]; skippedEmpty: number }> => {
    const oversize: File[] = [];
    let skippedEmpty = 0;
    const folderCache = new Map<string, number>();
    const tasks: UploadTask[] = [];

    for (const entry of entries) {
      if (entry.file.size > maxUploadBytes) {
        oversize.push(entry.file);
        continue;
      }
      if (entry.file.size <= 0) {
        skippedEmpty++;
        continue;
      }

      const rel = entry.relativePath ?? fileRelativePath(entry.file);
      const { dirParts } = rel ? parseRelativePath(rel) : { dirParts: [] as string[] };

      let targetParentId = parentId;
      for (const dirName of dirParts) {
        targetParentId = await ensureFolder(dirName, targetParentId, folderCache);
      }

      tasks.push({
        file: entry.file,
        relativePath: rel,
        targetParentId,
      });
    }

    return { tasks, oversize, skippedEmpty };
  };

  const markUploadCancelled = (task: Pick<UploadTask, "file" | "relativePath">, fileId?: number) => {
    setUploads((prev) =>
      prev.map((j) =>
        matchesUploadJob(j, task) && !isUploadTerminal(j.phase)
          ? patchUploadJob(j, { phase: "cancelled", fileId: fileId ?? j.fileId })
          : j
      )
    );
  };

  const cancelUploadFile = (job: UploadJob) => {
    uploadControllersRef.current.get(uploadEntryKey(job))?.abort();
    setUploads((prev) => {
      const current = prev.find((j) => matchesUploadJob(j, job));
      if (current?.fileId) void cleanupUploadOnServer(current.fileId);
      return prev.map((j) =>
        matchesUploadJob(j, job) && !isUploadTerminal(j.phase)
          ? patchUploadJob(j, { phase: "cancelled", fileId: current?.fileId ?? j.fileId })
          : j
      );
    });
    void load();
  };

  const cancelAllUploads = () => {
    setUploads((prev) => {
      for (const job of prev) {
        if (isUploadTerminal(job.phase)) continue;
        uploadControllersRef.current.get(uploadEntryKey(job))?.abort();
        if (job.fileId) void cleanupUploadOnServer(job.fileId);
      }
      return prev.map((j) =>
        !isUploadTerminal(j.phase) ? patchUploadJob(j, { phase: "cancelled" }) : j
      );
    });
    void load();
  };

  const cancelDownloadTransfer = () => {
    downloadCancelledRef.current = true;
    downloadAbortRef.current?.abort();
    setDownloadJob((prev) => (prev ? { ...prev, phase: "cancelled" } : prev));
  };

  const uploadSingleFile = async (task: UploadTask) => {
    const { file, targetParentId, relativePath } = task;
    const key = uploadEntryKey(task);
    let controller = uploadControllersRef.current.get(key);
    if (!controller) {
      controller = new AbortController();
      uploadControllersRef.current.set(key, controller);
    }
    const signal = controller.signal;

    if (signal.aborted) {
      markUploadCancelled(task);
      return;
    }

    const totalChunks = chunkCount(file.size, chunkSizeBytes);
    const startedAt = Date.now();
    let fileId: number | undefined;

    setUploads((prev) =>
      prev.map((j) =>
        matchesUploadJob(j, task)
          ? patchUploadJob({ ...j, startedAt, phase: "uploading" }, { phase: "uploading" })
          : j
      )
    );

    try {
      cloudLog("Iniciando upload", {
        nome: uploadDisplayName(task),
        tamanho: file.size,
        chunks: totalChunks,
        parent_id: targetParentId,
      });
      throwIfAborted(signal);
      const startRes = await api.cloudUploadStart(
        {
          name: file.name,
          parent_id: targetParentId,
          size_bytes: file.size,
          total_chunks: totalChunks,
          mime_type: file.type || null,
        },
        signal
      );
      fileId = startRes.file_id;

      if (startRes.renamed_from && startRes.name !== startRes.renamed_from) {
        setUploadNotice(
          `"${startRes.renamed_from}" já existia — enviando como "${startRes.name}".`
        );
      }

      cloudLog("upload/start OK", {
        file_id: fileId,
        nome: startRes.name,
        renamed_from: startRes.renamed_from,
      });

      setUploads((prev) =>
        prev.map((j) => (matchesUploadJob(j, task) ? { ...j, fileId } : j))
      );

      const doneSet = new Set<number>();
      try {
        const initial = await api.cloudUploadProgress(fileId, signal);
        initial.received_indices.forEach((idx) => doneSet.add(idx));
        if (doneSet.size > 0) {
          setUploads((prev) =>
            prev.map((j) =>
              matchesUploadJob(j, task)
                ? patchUploadJob(j, { chunksDone: doneSet.size, fileId })
                : j
            )
          );
        }
      } catch (e) {
        if (isAbortError(e)) throw e;
        cloudWarn("Progresso indisponível após start — enviando todos os fragmentos", {
          file_id: fileId,
          erro: e,
        });
      }

      for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
        throwIfAborted(signal);
        if (doneSet.has(chunkIndex)) continue;

        const blob = await readFileChunk(file, chunkIndex, chunkSizeBytes);
        await uploadChunkWithRetry(fileId, chunkIndex, blob, signal);
        doneSet.add(chunkIndex);

        const done = doneSet.size;
        setUploads((prev) =>
          prev.map((j) =>
            matchesUploadJob(j, task)
              ? patchUploadJob(j, {
                  fileId,
                  chunksDone: done,
                  phase: "uploading",
                })
              : j
          )
        );
      }

      setUploads((prev) =>
        prev.map((j) =>
          matchesUploadJob(j, task)
            ? patchUploadJob(j, {
                fileId,
                chunksDone: totalChunks,
                phase: "syncing",
              })
            : j
        )
      );

      const synced = await waitForDiscordSync(
        fileId,
        totalChunks,
        (syncedCount, receivedCount) => {
          setUploads((prev) =>
            prev.map((j) =>
              matchesUploadJob(j, task)
                ? patchUploadJob(j, {
                    fileId,
                    chunksDone: Math.max(j.chunksDone, receivedCount),
                    syncDone: syncedCount,
                    phase: "syncing",
                  })
                : j
            )
          );
        },
        signal
      );

      throwIfAborted(signal);

      setUploads((prev) =>
        prev.map((j) =>
          matchesUploadJob(j, task)
            ? patchUploadJob(j, {
                fileId,
                chunksDone: totalChunks,
                syncDone: synced.synced_chunks,
                phase: "finalizing",
              })
            : j
        )
      );

      await api.cloudUploadComplete(fileId, signal);
      cloudLog("Upload completo!", { file_id: fileId, nome: uploadDisplayName(task) });
      setUploads((prev) =>
        prev.map((j) =>
          matchesUploadJob(j, task)
            ? patchUploadJob(j, {
                fileId,
                chunksDone: totalChunks,
                syncDone: totalChunks,
                phase: "done",
              })
            : j
        )
      );
    } catch (e) {
      if (isAbortError(e)) {
        cloudLog("Upload cancelado", { nome: uploadDisplayName(task), file_id: fileId });
        markUploadCancelled(task, fileId);
        await cleanupUploadOnServer(fileId);
        return;
      }
      cloudError("Upload falhou", { nome: uploadDisplayName(task), erro: e });
      setError(e instanceof Error ? e.message : "Falha no upload");
      setUploads((prev) =>
        prev.map((j) =>
          matchesUploadJob(j, task)
            ? {
                ...j,
                fileId: fileId ?? j.fileId,
                phase: "error" as const,
                error: e instanceof Error ? e.message : "Falha no upload",
              }
            : j
        )
      );
    } finally {
      uploadControllersRef.current.delete(key);
    }
  };

  const uploadEntries = async (entries: FileUploadEntry[]) => {
    if (!entries.length) {
      cloudWarn("Nenhum arquivo selecionado");
      return;
    }

    cloudLog("uploadEntries", {
      quantidade: entries.length,
      nomes: entries.slice(0, 10).map((e) => uploadDisplayName(e)),
    });
    setUploadNotice("");

    let tasks: UploadTask[];
    let oversize: File[];
    let skippedEmpty: number;

    try {
      ({ tasks, oversize, skippedEmpty } = await buildUploadTasks(entries));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao preparar pastas para upload");
      return;
    }

    const notices: string[] = [];
    if (oversize.length) notices.push(formatOversizeNotice(oversize, maxUploadBytes));
    if (skippedEmpty > 0) {
      notices.push(
        skippedEmpty === 1
          ? "1 arquivo vazio foi ignorado."
          : `${skippedEmpty} arquivos vazios foram ignorados.`
      );
    }
    if (notices.length) setUploadNotice(notices.join(" "));

    if (!tasks.length) {
      if (!notices.length) cloudWarn("Nenhum arquivo válido para upload");
      return;
    }

    const jobs: UploadJob[] = tasks.map((task) => ({
      file: task.file,
      relativePath: task.relativePath,
      targetParentId: task.targetParentId,
      progress: 0,
      phase: "pending" as const,
      chunksDone: 0,
      totalChunks: chunkCount(task.file.size, chunkSizeBytes),
      syncDone: 0,
      chunkSizeBytes,
      startedAt: Date.now(),
      speedBps: 0,
      lastMetricAt: 0,
      lastMetricBytes: 0,
    }));
    setUploads((prev) => [...prev, ...jobs]);
    setUploadPanelExpanded(tasks.length <= 1);
    tasks.forEach((task) => {
      uploadControllersRef.current.set(uploadEntryKey(task), new AbortController());
    });

    await runUploadPool(tasks, uploadSingleFile, MAX_CONCURRENT_UPLOADS);

    await load();
  };

  const uploadFiles = (fileList: FileList | File[]) =>
    uploadEntries(collectFilesFromFileList(fileList));

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    try {
      const entries = await collectFilesFromDataTransfer(e.dataTransfer);
      cloudLog("CLIQUE drag-and-drop", { arquivos: entries.length });
      if (entries.length) await uploadEntries(entries);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao ler arquivos soltos");
    }
  };

  const createFolder = async () => {
    const name = folderName.trim();
    if (!name) return;
    setCreatingFolder(true);
    try {
      await api.cloudCreateFolder({ name, parent_id: parentId });
      setFolderName("");
      setShowFolderModal(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao criar pasta");
    } finally {
      setCreatingFolder(false);
    }
  };

  const viewTextFile = async (item: CloudFileItem) => {
    if (!canPreviewTextFile(item)) {
      if (isTextFile(item) && item.size_bytes > 0) {
        setError(
          `Arquivo grande demais para visualizar (máx. ${textPreviewLimitLabel()}). Use Baixar.`
        );
      }
      return;
    }
    setTextPreview({ item, content: "", loading: true, error: "" });
    try {
      const blob = await api.cloudDownload(item.id);
      const text = await blob.text();
      setTextPreview({ item, content: text, loading: false, error: "" });
    } catch (e) {
      setTextPreview({
        item,
        content: "",
        loading: false,
        error: e instanceof Error ? e.message : "Erro ao abrir arquivo",
      });
    }
  };

  const downloadFile = async (item: CloudFileItem) => {
    if (downloadJob) return;
    cloudLog("CLIQUE baixar", { id: item.id, nome: item.name });
    setError("");

    downloadCancelledRef.current = false;
    const controller = new AbortController();
    downloadAbortRef.current = controller;

    const job: DownloadJob = {
      id: item.id,
      name: item.name,
      sizeBytes: item.size_bytes,
      mimeType: item.mime_type,
      phase: "preparing",
      progress: 0,
      loadedBytes: 0,
      totalBytes: item.size_bytes > 0 ? item.size_bytes : null,
      startedAt: Date.now(),
    };
    setDownloadJob(job);

    try {
      const blob = await api.cloudDownloadWithProgress(
        item.id,
        (loaded, total) => {
          setDownloadJob((prev) => {
            if (!prev || prev.id !== item.id) return prev;
            const knownTotal = total ?? (item.size_bytes > 0 ? item.size_bytes : null);
            const progress =
              knownTotal && knownTotal > 0
                ? Math.min(99, Math.round((loaded / knownTotal) * 100))
                : loaded > 0
                  ? 50
                  : 5;
            return {
              ...prev,
              phase: "downloading",
              loadedBytes: loaded,
              totalBytes: knownTotal,
              progress,
            };
          });
        },
        controller.signal
      );

      if (downloadCancelledRef.current || controller.signal.aborted) {
        setDownloadJob((prev) => (prev ? { ...prev, phase: "cancelled", progress: 100 } : prev));
        return;
      }

      setDownloadJob((prev) =>
        prev
          ? {
              ...prev,
              phase: "saving",
              progress: 100,
              loadedBytes: blob.size,
              totalBytes: blob.size,
            }
          : prev
      );

      const result = await saveFileAfterDownload(blob, item.name, item.mime_type);

      if (downloadCancelledRef.current || controller.signal.aborted) {
        setDownloadJob((prev) => (prev ? { ...prev, phase: "cancelled", progress: 100 } : prev));
        return;
      }

      if (result === "cancelled") {
        setDownloadJob((prev) =>
          prev ? { ...prev, phase: "cancelled", progress: 100 } : prev
        );
      } else {
        cloudLog("Download salvo", { id: item.id, nome: item.name });
        setDownloadJob((prev) => (prev ? { ...prev, phase: "done", progress: 100 } : prev));
      }
    } catch (e) {
      if (isAbortError(e) || downloadCancelledRef.current) {
        setDownloadJob((prev) => (prev ? { ...prev, phase: "cancelled" } : prev));
        return;
      }
      cloudError("Download falhou", { id: item.id, erro: e });
      const msg = e instanceof Error ? e.message : "Erro ao baixar arquivo";
      setError(msg);
      setDownloadJob((prev) =>
        prev ? { ...prev, phase: "error", error: msg } : prev
      );
    } finally {
      downloadAbortRef.current = null;
    }
  };

  const cleanupIncomplete = async () => {
    cloudLog("CLIQUE limpar incompletos");
    if (!confirm("Remover todos os uploads incompletos desta pasta?")) return;
    try {
      const { removed } = await api.cloudCleanupIncomplete(parentId);
      cloudLog("Incompletos removidos", { removed });
      await load();
      setError(removed > 0 ? `${removed} upload(s) incompleto(s) removido(s).` : "Nenhum incompleto encontrado.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao limpar incompletos");
    }
  };

  const deleteItem = async (item: CloudFileItem) => {
    cloudLog("CLIQUE excluir", { id: item.id, nome: item.name, pasta: item.is_folder });
    const label = item.is_folder ? "pasta" : "arquivo";
    if (!confirm(`Excluir ${label} "${item.name}"?`)) {
      cloudLog("Exclusão cancelada pelo usuário");
      return;
    }
    setDeletingId(item.id);
    try {
      await api.cloudDelete(item.id);
      cloudLog("Excluído com sucesso", { id: item.id });
      await load();
    } catch (e) {
      cloudError("Exclusão falhou", { id: item.id, erro: e });
      setError(e instanceof Error ? e.message : "Erro ao excluir");
    } finally {
      setDeletingId(null);
    }
  };

  const purchaseStorage = async (slug: string) => {
    setPurchasingSlug(slug);
    setError("");
    try {
      const result = await api.cloudStoragePurchase(slug);
      if (result.status === "pending_payment") {
        sessionStorage.setItem(STORAGE_PENDING_ORDER_KEY, String(result.order_id));
        setPendingPix({
          orderId: result.order_id,
          brCode: result.pix_br_code ?? null,
          qrBase64: result.pix_qr_base64 ?? null,
          expiresAt: result.pix_expires_at ?? null,
          amountCents: result.total_cents,
        });
        setPixOpen(true);
        return;
      }
      await load();
      setUploadNotice(`+${result.extra_gb} GB/mês adicionados ao seu CyberCloud.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao contratar espaço");
    } finally {
      setPurchasingSlug(null);
    }
  };

  const renewStorage = async () => {
    if (!renewQuote) return;
    setRenewLoading(true);
    setRenewError("");
    try {
      const result = await api.cloudStorageRenew(renewMonths);
      if (result.status === "pending_payment") {
        sessionStorage.setItem(STORAGE_PENDING_ORDER_KEY, String(result.order_id));
        setPendingPix({
          orderId: result.order_id,
          brCode: result.pix_br_code ?? null,
          qrBase64: result.pix_qr_base64 ?? null,
          expiresAt: result.pix_expires_at ?? null,
          amountCents: result.total_cents,
        });
        setPixOpen(true);
        return;
      }
      await load();
      setUploadNotice("Renovação CyberCloud confirmada.");
    } catch (e) {
      setRenewError(e instanceof Error ? e.message : "Erro ao renovar CyberCloud");
    } finally {
      setRenewLoading(false);
    }
  };

  const cloudBilling = quota?.billing;
  const cloudBillingBadgeClass =
    cloudBilling?.billing_state === "active"
      ? "text-[var(--success)] bg-[var(--success)]/10 border-[var(--success)]/20"
      : cloudBilling?.billing_state === "grace"
        ? "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/20"
        : cloudBilling?.billing_state === "suspended"
          ? "text-[var(--danger)] bg-[var(--danger)]/10 border-[var(--danger)]/20"
          : "text-muted bg-[var(--bg-elevated)] border-[var(--glass-border)]";

  const quotaPercent = quota
    ? Math.min(100, Math.round((quota.used_bytes / quota.quota_bytes) * 100))
    : 0;

  const activeUploads = uploads.filter(
    (u) =>
      u.phase === "pending" ||
      u.phase === "uploading" ||
      u.phase === "syncing" ||
      u.phase === "finalizing" ||
      u.phase === "done" ||
      u.phase === "error" ||
      u.phase === "cancelled"
  );

  const uploadBatchStats = useMemo(() => {
    void uploadTick;
    return computeUploadBatchStats(uploads);
  }, [uploads, uploadTick]);

  const uploadBatchFinished =
    uploadBatchStats.total > 0 &&
    uploadBatchStats.completed +
      uploadBatchStats.failed +
      uploadBatchStats.cancelled >=
      uploadBatchStats.total;

  const uploadBatchActive = uploads.some((j) => !isUploadTerminal(j.phase));

  const downloadFinished =
    downloadJob !== null &&
    (downloadJob.phase === "done" ||
      downloadJob.phase === "cancelled" ||
      downloadJob.phase === "error");

  useEffect(() => {
    if (!uploadBatchFinished) return;
    const delay = uploadBatchStats.failed > 0 ? UPLOAD_ERROR_CLOSE_MS : UPLOAD_CLOSE_MS;
    const timer = window.setTimeout(() => setUploads([]), delay);
    return () => window.clearTimeout(timer);
  }, [uploadBatchFinished, uploadBatchStats.failed]);

  useEffect(() => {
    if (!downloadJob || downloadFinished) return;
    const interval = window.setInterval(() => setDownloadTick((t) => t + 1), 1000);
    return () => window.clearInterval(interval);
  }, [downloadJob?.id, downloadFinished]);

  useEffect(() => {
    if (!downloadFinished || !downloadJob) return;
    const delay =
      downloadJob.phase === "error" ? DOWNLOAD_ERROR_CLOSE_MS : DOWNLOAD_CLOSE_MS;
    const timer = window.setTimeout(() => setDownloadJob(null), delay);
    return () => window.clearTimeout(timer);
  }, [downloadFinished, downloadJob?.phase, downloadJob?.id]);

  useEffect(() => {
    if (!activeUploads.length) return;
    const interval = window.setInterval(() => setUploadTick((t) => t + 1), 1000);
    return () => window.clearInterval(interval);
  }, [activeUploads.length]);

  const incompleteCount = items.filter(
    (i) => !i.is_folder && i.upload_status === "uploading"
  ).length;

  const tabBtn = (id: CloudTab, label: string) => (
    <button
      type="button"
      onClick={() => setActiveTab(id)}
      className={`px-4 py-2 rounded-xl text-sm font-medium transition ${
        activeTab === id ? "btn-primary !py-2" : "btn-ghost !py-2"
      }`}
    >
      {label}
    </button>
  );

  const billingNeedsAttention =
    cloudBilling &&
    cloudBilling.contracted_gb > 0 &&
    cloudBilling.paid_until &&
    (cloudBilling.billing_state === "grace" || cloudBilling.billing_state === "suspended");

  return (
    <div className="space-y-6">
      {uploadNotice && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {uploadNotice}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-[var(--danger)]/30 bg-[var(--danger)]/10 px-4 py-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {tabBtn("files", "Arquivos & status")}
        {tabBtn("billing", "Plano & pagamento")}
      </div>

      {activeTab === "files" && (
        <>
          {quota && (
            <div className="glass-card p-5 space-y-4">
              <div>
                <p className="text-xs text-muted uppercase tracking-wider">Uso do CyberCloud</p>
                <p className="text-lg font-semibold mt-0.5">
                  {formatBytes(quota.used_bytes)}{" "}
                  <span className="text-muted font-normal">de {formatBytes(quota.quota_bytes)}</span>
                </p>
                <p className="text-xs text-muted mt-2">
                  <button
                    type="button"
                    onClick={() => setActiveTab("billing")}
                    className="text-[var(--accent)] hover:underline"
                  >
                    Ver plano e pagamento
                  </button>
                </p>
              </div>

              <div className="h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-400 transition-all duration-500"
                  style={{ width: `${quotaPercent}%` }}
                />
              </div>
              <p className="text-xs text-muted">{quotaPercent}% utilizado</p>

              {billingNeedsAttention && (
                <div className="rounded-xl border border-[var(--warning)]/30 bg-[var(--warning)]/10 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-[var(--warning)]">
                    {cloudBilling!.billing_state === "grace"
                      ? `Mensalidade vencida. Carência de ${cloudBilling!.days_in_grace_left} dia(s).`
                      : "Espaço contratado suspenso. Renove para voltar a usar os GB pagos."}
                  </p>
                  <button
                    type="button"
                    onClick={() => setActiveTab("billing")}
                    className="btn-primary text-sm !py-2 shrink-0"
                  >
                    Renovar agora
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="glass-card p-4 sm:p-5 border border-[var(--accent)]/20 bg-[var(--accent)]/5">
            <p className="text-sm text-secondary leading-relaxed">
              Envie arquivos e pastas com segurança. Até{" "}
              <span className="font-medium text-[var(--text-primary)]">
                {formatBytes(maxUploadBytes)}
              </span>{" "}
              por arquivo, com até {MAX_CONCURRENT_UPLOADS} transferências ao mesmo tempo. Cada VPS ativa
              aumenta seu espaço na nuvem — contrate pacotes extras na aba Plano & pagamento.
            </p>
          </div>

          <div
            className={`glass-card overflow-hidden transition-colors ${
              dragOver ? "border-[var(--accent)] ring-2 ring-[var(--accent)]/30" : ""
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
          >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 border-b border-[var(--glass-border)]">
          <nav className="flex items-center gap-1 flex-wrap text-sm min-w-0">
            {breadcrumb.map((crumb, index) => (
              <span key={`${crumb.id}-${index}`} className="flex items-center gap-1">
                {index > 0 && <span className="text-muted">/</span>}
                <button
                  type="button"
                  onClick={() => navigateTo(index)}
                  className={`flex items-center gap-1 px-2 py-1 rounded-md hover:bg-[var(--bg-elevated)] transition-colors truncate max-w-[140px] sm:max-w-none ${
                    index === breadcrumb.length - 1
                      ? "font-semibold text-[var(--text-primary)]"
                      : "text-secondary"
                  }`}
                >
                  {index === 0 && <SvgHome className="w-4 h-4 shrink-0" />}
                  {crumb.name}
                </button>
              </span>
            ))}
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            {incompleteCount > 0 && (
              <button
                type="button"
                onClick={cleanupIncomplete}
                className="btn-ghost px-3 py-2 text-[var(--warning)]"
                title="Remover uploads travados"
              >
                Limpar {incompleteCount} incompleto{incompleteCount > 1 ? "s" : ""}
              </button>
            )}
            <button type="button" onClick={() => { cloudLog("CLIQUE atualizar"); load(); }} className="btn-ghost px-3 py-2" title="Atualizar">
              <SvgRefresh className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => { cloudLog("CLIQUE nova pasta"); setShowFolderModal(true); }}
              className="btn-ghost px-3 py-2"
            >
              <SvgPlus className="w-4 h-4" />
              <span className="hidden sm:inline">Nova pasta</span>
            </button>
            <button
              type="button"
              onClick={() => {
                cloudLog("CLIQUE botão Enviar pasta");
                folderInputRef.current?.click();
              }}
              className="btn-ghost px-3 py-2"
            >
              <SvgFolder className="w-4 h-4" />
              <span className="hidden sm:inline">Enviar pasta</span>
            </button>
            <button
              type="button"
              onClick={() => {
                cloudLog("CLIQUE botão Enviar — abrindo seletor de arquivos");
                fileInputRef.current?.click();
              }}
              className="btn-primary px-3 py-2"
            >
              <SvgUpload className="w-4 h-4" />
              Enviar
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                cloudLog("Arquivos selecionados no input", { quantidade: e.target.files?.length ?? 0 });
                if (e.target.files?.length) void uploadFiles(e.target.files);
                e.target.value = "";
              }}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                cloudLog("Pasta selecionada no input", { quantidade: e.target.files?.length ?? 0 });
                if (e.target.files?.length) void uploadEntries(collectFilesFromFileList(e.target.files));
                e.target.value = "";
              }}
              {...({ webkitdirectory: "", directory: "" } as React.InputHTMLAttributes<HTMLInputElement>)}
            />
          </div>
        </div>

        {loading ? (
          <PageLoader label="Carregando arquivos…" compact framed={false} />
        ) : items.length === 0 ? (
          <div
            className="text-center py-16 px-6 cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-[var(--accent)]/10 flex items-center justify-center">
              <SvgUpload className="w-7 h-7 text-[var(--accent)]" />
            </div>
            <h3 className="font-semibold mb-1">Nenhum arquivo aqui</h3>
            <p className="text-sm text-muted mb-1">
              Arraste arquivos ou pastas para esta área, ou use Enviar / Enviar pasta.
            </p>
            <p className="text-xs text-muted">
              Até {formatBytes(maxUploadBytes)} por arquivo (acima disso o arquivo é ignorado). Pastas
              criam subpastas automaticamente.
            </p>
          </div>
        ) : (
          <>
            <div className="px-4 py-3 border-b border-[var(--glass-border)] flex flex-col lg:flex-row gap-3 lg:items-center lg:justify-between">
              <div className="flex flex-col sm:flex-row gap-2 flex-1 min-w-0">
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Pesquisar por nome…"
                  className="input-glass w-full sm:max-w-xs text-sm"
                />
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
                  className="input-glass text-sm w-full sm:w-auto"
                  aria-label="Filtrar por tipo"
                >
                  <option value="all">Todos</option>
                  <option value="folders">Pastas</option>
                  <option value="files">Arquivos</option>
                  <option value="incomplete">Incompletos</option>
                </select>
              </div>
              <p className="text-xs text-muted shrink-0">
                {displayItems.length} de {items.length} item(ns)
                {searchQuery.trim() || typeFilter !== "all" ? " (filtrado)" : ""}
              </p>
            </div>

            {selectedIds.size > 0 && (
              <div className="px-4 py-2.5 border-b border-[var(--glass-border)] bg-[var(--accent)]/5 flex flex-wrap items-center gap-2">
                <span className="text-sm text-secondary mr-1">
                  {selectedIds.size} selecionado{selectedIds.size > 1 ? "s" : ""}
                </span>
                <button
                  type="button"
                  onClick={openMoveModal}
                  disabled={bulkBusy}
                  className="btn-ghost px-3 py-1.5 text-sm"
                >
                  Mover
                </button>
                <button
                  type="button"
                  onClick={deleteSelected}
                  disabled={bulkBusy}
                  className="btn-ghost px-3 py-1.5 text-sm text-[var(--danger)]"
                >
                  Excluir
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedIds(new Set())}
                  disabled={bulkBusy}
                  className="btn-ghost px-3 py-1.5 text-sm ml-auto"
                >
                  Limpar seleção
                </button>
              </div>
            )}

            {displayItems.length === 0 ? (
              <div className="text-center py-12 px-6 text-sm text-muted">
                Nenhum item corresponde à pesquisa ou filtro.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted uppercase tracking-wider border-b border-[var(--glass-border)]">
                      <th className="px-4 py-3 w-10">
                        <input
                          type="checkbox"
                          checked={allVisibleSelected}
                          ref={(el) => {
                            if (el) el.indeterminate = someVisibleSelected;
                          }}
                          onChange={toggleSelectAll}
                          aria-label="Selecionar todos"
                          className="rounded border-[var(--glass-border)] accent-[var(--accent)]"
                        />
                      </th>
                      <th className="px-4 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("name")}
                          className="inline-flex items-center gap-1 hover:text-[var(--text-primary)] transition-colors"
                        >
                          Nome
                          <span className="text-[10px] opacity-70">
                            {sortIndicator(sortField === "name", sortDir)}
                          </span>
                        </button>
                      </th>
                      <th className="px-4 py-3 font-medium hidden sm:table-cell">
                        <button
                          type="button"
                          onClick={() => toggleSort("size")}
                          className="inline-flex items-center gap-1 hover:text-[var(--text-primary)] transition-colors"
                        >
                          Tamanho
                          <span className="text-[10px] opacity-70">
                            {sortIndicator(sortField === "size", sortDir)}
                          </span>
                        </button>
                      </th>
                      <th className="px-4 py-3 font-medium hidden md:table-cell">Status</th>
                      <th className="px-4 py-3 font-medium hidden lg:table-cell">
                        <button
                          type="button"
                          onClick={() => toggleSort("updated")}
                          className="inline-flex items-center gap-1 hover:text-[var(--text-primary)] transition-colors"
                        >
                          Modificado
                          <span className="text-[10px] opacity-70">
                            {sortIndicator(sortField === "updated", sortDir)}
                          </span>
                        </button>
                      </th>
                      <th className="px-4 py-3 font-medium text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayItems.map((item) => {
                      const selected = selectedIds.has(item.id);
                      return (
                        <tr
                          key={item.id}
                          className={`border-b border-[var(--glass-border)]/60 transition-colors ${
                            selected
                              ? "bg-[var(--accent)]/10"
                              : "hover:bg-[var(--bg-elevated)]/40"
                          }`}
                        >
                          <td className="px-4 py-3">
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => toggleSelect(item.id)}
                              aria-label={`Selecionar ${item.name}`}
                              className="rounded border-[var(--glass-border)] accent-[var(--accent)]"
                            />
                          </td>
                          <td className="px-4 py-3">
                            {item.is_folder ? (
                              <button
                                type="button"
                                onClick={() => openFolder(item)}
                                className="flex items-center gap-2.5 text-left group"
                              >
                                <span className="text-[var(--warning)]">
                                  <SvgFolder className="w-5 h-5" />
                                </span>
                                <span className="font-medium group-hover:text-[var(--accent)] transition-colors truncate max-w-[180px] sm:max-w-xs">
                                  {item.name}
                                </span>
                              </button>
                            ) : (
                              <div className="flex items-center gap-2.5 min-w-0">
                                <span className="text-[var(--text-muted)] shrink-0">
                                  <SvgDocument className="w-5 h-5" />
                                </span>
                                {canPreviewTextFile(item) ? (
                                  <button
                                    type="button"
                                    onClick={() => void viewTextFile(item)}
                                    className="truncate max-w-[180px] sm:max-w-xs text-left font-medium hover:text-[var(--accent)] transition-colors"
                                    title="Visualizar texto"
                                  >
                                    {item.name}
                                  </button>
                                ) : (
                                  <span className="truncate max-w-[180px] sm:max-w-xs">{item.name}</span>
                                )}
                                {item.upload_status === "uploading" && (
                                  <span className="text-xs text-[var(--warning)] shrink-0">
                                    Enviando…
                                  </span>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-muted hidden sm:table-cell">
                            {item.is_folder ? "—" : formatBytes(item.size_bytes)}
                          </td>
                          <td className="px-4 py-3 text-muted hidden md:table-cell">
                            {item.is_folder
                              ? "—"
                              : item.upload_status === "ready"
                                ? "Disponível"
                                : item.upload_status === "uploading"
                                  ? "Enviando"
                                  : item.upload_status}
                          </td>
                          <td className="px-4 py-3 text-muted hidden lg:table-cell">
                            {formatDate(item.updated_at)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center justify-end gap-1">
                              {!item.is_folder && item.upload_status === "ready" && (
                                <>
                                  {canPreviewTextFile(item) && (
                                    <button
                                      type="button"
                                      onClick={() => void viewTextFile(item)}
                                      className="p-2 rounded-lg hover:bg-[var(--bg-elevated)] text-muted hover:text-[var(--accent)] transition-colors"
                                      title="Visualizar texto"
                                    >
                                      <SvgEye className="w-4 h-4" />
                                    </button>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => downloadFile(item)}
                                    disabled={downloadJob !== null}
                                    className="p-2 rounded-lg hover:bg-[var(--bg-elevated)] text-muted hover:text-[var(--accent)] transition-colors disabled:opacity-50"
                                    title={
                                      downloadJob !== null ? "Download em andamento…" : "Baixar"
                                    }
                                  >
                                    <SvgDownload className="w-4 h-4" />
                                  </button>
                                </>
                              )}
                              <button
                                type="button"
                                onClick={() => deleteItem(item)}
                                disabled={deletingId === item.id || bulkBusy}
                                className="p-2 rounded-lg hover:bg-[var(--danger)]/10 text-muted hover:text-[var(--danger)] transition-colors disabled:opacity-50"
                                title="Excluir"
                              >
                                <SvgTrash className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
        </>
      )}

      {activeTab === "billing" && (
        quota ? (
          <div className="glass-card p-5 space-y-4">
            <div>
              <p className="text-xs text-muted uppercase tracking-wider">Plano CyberCloud</p>
              <p className="text-lg font-semibold mt-0.5">
                {formatBytes(quota.used_bytes)}{" "}
                <span className="text-muted font-normal">de {formatBytes(quota.quota_bytes)}</span>
              </p>
              <p className="text-xs text-muted mt-2 leading-relaxed">
                Toda conta inclui {formatBytes(quota.base_bytes)} na nuvem.
                {quota.vps_bonus_bytes > 0 && (
                  <> Seus planos (VPS e sites) somam +{formatBytes(quota.vps_bonus_bytes)}.</>
                )}
                {quota.subscribed_bytes > 0 && (
                  <> Espaço contratado: +{formatBytes(quota.subscribed_bytes)}/mês.</>
                )}
                {quota.bonus_bytes > 0 && (
                  <> Cortesia: +{formatBytes(quota.bonus_bytes)}.</>
                )}
              </p>
            </div>

            {cloudBilling && cloudBilling.contracted_gb > 0 && cloudBilling.paid_until && (
              <div
                className={`rounded-xl border px-4 py-3 flex flex-wrap justify-between gap-3 items-center ${cloudBillingBadgeClass}`}
              >
                <div>
                  <p className="font-semibold text-sm">{cloudBilling.billing_label}</p>
                  <p className="text-xs opacity-90">
                    Vencimento:{" "}
                    {new Date(cloudBilling.paid_until).toLocaleDateString("pt-BR", {
                      day: "2-digit",
                      month: "long",
                      year: "numeric",
                    })}
                    {cloudBilling.billing_day > 0 && (
                      <span className="block mt-0.5">Todo dia {cloudBilling.billing_day} de cada mês</span>
                    )}
                  </p>
                </div>
                {cloudBilling.monthly_cents > 0 && (
                  <p className="text-base font-bold">
                    {formatPrice(cloudBilling.monthly_cents)}
                    <span className="text-sm font-normal opacity-80">/mês</span>
                  </p>
                )}
              </div>
            )}

            {billingNeedsAttention && (
              <p className="text-sm text-[var(--warning)]">
                {cloudBilling!.billing_state === "grace"
                  ? `Mensalidade vencida. Carência de ${cloudBilling!.days_in_grace_left} dia(s) antes de suspender o espaço contratado.`
                  : "Espaço contratado suspenso. Renove para voltar a usar os GB pagos."}
              </p>
            )}

            {cloudBilling && cloudBilling.contracted_gb > 0 && cloudBilling.paid_until && (
              <div className="rounded-xl border border-[var(--glass-border)]/60 p-4 space-y-3">
                <p className="text-sm font-medium">Renovar CyberCloud</p>
                <div className="flex flex-wrap gap-3 items-end">
                  <label className="text-xs">
                    Meses
                    <select
                      value={renewMonths}
                      onChange={(e) => setRenewMonths(Number(e.target.value))}
                      className="input-glass block mt-1 min-w-[88px]"
                    >
                      {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </label>
                  {renewQuote && (
                    <div className="text-sm">
                      <p>
                        Total: <strong>{formatPrice(renewQuote.total_cents)}</strong>
                        {renewQuote.monthly_cents > 0 && (
                          <span className="text-muted">
                            {" "}
                            ({formatPrice(renewQuote.monthly_cents)}/mês)
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-muted">
                        Novo vencimento:{" "}
                        {new Date(renewQuote.new_paid_until).toLocaleDateString("pt-BR")}
                      </p>
                    </div>
                  )}
                  <button
                    type="button"
                    disabled={renewLoading || !renewQuote}
                    onClick={renewStorage}
                    className="btn-primary text-sm !py-2"
                  >
                    {renewLoading ? <BusyLabel>Processando…</BusyLabel> : "Renovar"}
                  </button>
                </div>
                {renewError && <p className="text-xs text-[var(--danger)]">{renewError}</p>}
              </div>
            )}

            <div className="h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-400 transition-all duration-500"
                style={{ width: `${quotaPercent}%` }}
              />
            </div>
            <p className="text-xs text-muted">{quotaPercent}% do espaço utilizado</p>

            {storagePackages.length > 0 && (
              <div className="pt-2 border-t border-[var(--glass-border)]/60">
                <p className="text-sm font-medium text-[var(--text-primary)] mb-2">
                  Contratar mais espaço
                </p>
                <p className="text-xs text-muted mb-2">
                  Assinatura mensal. Primeira cobrança proporcional aos dias até o vencimento (VPS ou CyberCloud).
                </p>
                <div className="flex flex-wrap gap-2">
                  {storagePackages.map((pkg) => (
                    <button
                      key={pkg.slug}
                      type="button"
                      disabled={purchasingSlug !== null}
                      onClick={() => purchaseStorage(pkg.slug)}
                      className="btn-ghost px-3 py-2 text-sm border border-[var(--glass-border)]"
                    >
                      {purchasingSlug === pkg.slug ? (
                        <BusyLabel>Redirecionando…</BusyLabel>
                      ) : (
                        `+${pkg.gb} GB · ${formatPrice(pkg.price_cents)}/mês`
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <InlineLoader label="Carregando plano…" />
        )
      )}

      {showMoveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="glass-card w-full max-w-lg p-6 max-h-[85vh] flex flex-col">
            <h3 className="text-lg font-semibold mb-1">Mover itens</h3>
            <p className="text-sm text-muted mb-4">
              {selectedIds.size} item(ns) → escolha a pasta de destino
            </p>

            <nav className="flex items-center gap-1 flex-wrap text-sm mb-3 min-w-0">
              {moveBrowseBreadcrumb.map((crumb, index) => (
                <span key={`move-${crumb.id}-${index}`} className="flex items-center gap-1">
                  {index > 0 && <span className="text-muted">/</span>}
                  <button
                    type="button"
                    onClick={() => navigateMoveBrowse(index)}
                    className={`px-2 py-1 rounded-md hover:bg-[var(--bg-elevated)] truncate max-w-[120px] ${
                      index === moveBrowseBreadcrumb.length - 1
                        ? "font-semibold text-[var(--text-primary)]"
                        : "text-secondary"
                    }`}
                  >
                    {index === 0 ? "Raiz" : crumb.name}
                  </button>
                </span>
              ))}
            </nav>

            <div className="flex-1 overflow-y-auto rounded-lg border border-[var(--glass-border)] min-h-[160px] max-h-[280px]">
              {moveBrowseLoading ? (
                <div className="p-6 flex justify-center">
                  <InlineLoader label="Carregando pastas…" />
                </div>
              ) : moveBrowseFolders.length === 0 ? (
                <p className="p-6 text-sm text-muted text-center">
                  Nenhuma subpasta aqui — você pode mover para este nível.
                </p>
              ) : (
                <ul className="divide-y divide-[var(--glass-border)]/60">
                  {moveBrowseFolders.map((folder) => (
                    <li key={folder.id}>
                      <button
                        type="button"
                        onClick={() => enterMoveFolder(folder)}
                        disabled={selectedIds.has(folder.id)}
                        className="w-full flex items-center gap-2.5 px-4 py-3 text-left hover:bg-[var(--bg-elevated)]/60 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <SvgFolder className="w-5 h-5 text-[var(--warning)] shrink-0" />
                        <span className="truncate">{folder.name}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <p className="text-xs text-muted mt-3">
              Destino:{" "}
              <span className="text-secondary">
                {moveBrowseBreadcrumb.map((c) => (c.id === null ? "Raiz" : c.name)).join(" / ")}
              </span>
            </p>

            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={() => setShowMoveModal(false)}
                disabled={bulkBusy}
                className="btn-ghost"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={moveSelected}
                disabled={bulkBusy}
                className="btn-primary"
              >
                {bulkBusy ? "Movendo…" : "Mover para cá"}
              </button>
            </div>
          </div>
        </div>
      )}

      {textPreview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60"
          onClick={() => setTextPreview(null)}
        >
          <div
            className="glass-card w-full max-w-3xl max-h-[min(85vh,720px)] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={`Visualizar ${textPreview.item.name}`}
          >
            <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-[var(--glass-border)] bg-[var(--bg-elevated)]/80">
              <div className="min-w-0">
                <p className="text-sm font-semibold truncate">{textPreview.item.name}</p>
                <p className="text-xs text-muted mt-0.5">
                  {formatBytes(textPreview.item.size_bytes)}
                  {textPreview.item.mime_type ? ` · ${textPreview.item.mime_type}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => downloadFile(textPreview.item)}
                  disabled={downloadJob !== null}
                  className="btn-ghost !py-1.5 !px-2.5 text-xs"
                >
                  Baixar
                </button>
                <button
                  type="button"
                  onClick={() => setTextPreview(null)}
                  className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-[var(--bg-base)] text-muted text-lg leading-none"
                  aria-label="Fechar"
                >
                  ×
                </button>
              </div>
            </div>
            <div className="flex-1 min-h-0 overflow-auto bg-[#0a0a0a]">
              {textPreview.loading ? (
                <div className="p-6 flex justify-center">
                  <InlineLoader label="Carregando conteúdo…" />
                </div>
              ) : textPreview.error ? (
                <p className="p-6 text-sm text-[var(--danger)]">{textPreview.error}</p>
              ) : textPreview.content.length === 0 ? (
                <p className="p-6 text-sm text-muted italic">Arquivo vazio</p>
              ) : (
                <pre className="p-4 text-xs sm:text-sm font-mono text-[var(--text-secondary)] whitespace-pre-wrap break-words leading-relaxed">
                  {textPreview.content}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}

      {showFolderModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="glass-card w-full max-w-md p-6">
            <h3 className="text-lg font-semibold mb-4">Nova pasta</h3>
            <input
              type="text"
              value={folderName}
              onChange={(e) => setFolderName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && createFolder()}
              placeholder="Nome da pasta"
              className="input-glass w-full mb-4"
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowFolderModal(false);
                  setFolderName("");
                }}
                className="btn-ghost"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={createFolder}
                disabled={creatingFolder || !folderName.trim()}
                className="btn-primary"
              >
                {creatingFolder ? <BusyLabel>Criando…</BusyLabel> : "Criar"}
              </button>
            </div>
          </div>
        </div>
      )}

      {uploads.length > 0 && (
        <div
          className="fixed bottom-4 right-4 z-40 w-[min(calc(100vw-2rem),24rem)] glass-card shadow-2xl border border-[var(--glass-border)] overflow-hidden"
          role="region"
          aria-label="Progresso de upload"
        >
          <div className="px-4 py-3 bg-[var(--bg-elevated)]/80 backdrop-blur-sm">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {uploadBatchFinished
                    ? uploadBatchStats.failed > 0
                      ? "Upload finalizado com erros"
                      : uploadBatchStats.cancelled === uploadBatchStats.total
                        ? "Upload cancelado"
                        : uploadBatchStats.cancelled > 0
                          ? "Upload finalizado"
                          : "Upload concluído"
                    : `Enviando ${uploadBatchStats.total} arquivo${uploadBatchStats.total > 1 ? "s" : ""}`}
                </p>
                <p className="text-xs text-muted mt-0.5">
                  {uploadBatchStats.completed}/{uploadBatchStats.total} concluído
                  {uploadBatchStats.total > 1 ? "s" : ""}
                  {uploadBatchStats.failed > 0 && (
                    <span className="text-[var(--danger)]">
                      {" "}
                      · {uploadBatchStats.failed} erro{uploadBatchStats.failed > 1 ? "s" : ""}
                    </span>
                  )}
                  {uploadBatchStats.cancelled > 0 && (
                    <span className="text-[var(--warning)]">
                      {" "}
                      · {uploadBatchStats.cancelled} cancelado
                      {uploadBatchStats.cancelled > 1 ? "s" : ""}
                    </span>
                  )}
                  {!uploadBatchFinished && uploadBatchStats.queued > 0 && (
                    <> · {uploadBatchStats.queued} na fila</>
                  )}
                  {!uploadBatchFinished && uploadBatchStats.active > 0 && (
                    <> · {uploadBatchStats.active} ativo{uploadBatchStats.active > 1 ? "s" : ""}</>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {uploadBatchActive && (
                  <button
                    type="button"
                    onClick={cancelAllUploads}
                    className="px-2 py-1 rounded-lg text-[11px] font-medium text-[var(--danger)] hover:bg-[var(--bg-base)] transition-colors"
                  >
                    Cancelar tudo
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setUploadPanelExpanded((v) => !v)}
                  className="p-1.5 rounded-lg hover:bg-[var(--bg-base)] text-muted hover:text-[var(--text-primary)] transition-colors"
                  aria-expanded={uploadPanelExpanded}
                  aria-label={uploadPanelExpanded ? "Recolher detalhes" : "Expandir detalhes"}
                >
                  <SvgChevronDown
                    className={`w-4 h-4 transition-transform duration-200 ${
                      uploadPanelExpanded ? "rotate-180" : ""
                    }`}
                  />
                </button>
              </div>
            </div>

            <div className="mt-2.5 h-2 rounded-full bg-[var(--bg-base)] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  uploadBatchFinished &&
                  (uploadBatchStats.failed > 0 ||
                    uploadBatchStats.cancelled === uploadBatchStats.total)
                    ? "bg-[var(--warning)]"
                    : uploadBatchFinished
                      ? "bg-emerald-500"
                      : "bg-gradient-to-r from-brand-500 to-[var(--accent)]"
                }`}
                style={{ width: `${uploadBatchStats.overallProgress}%` }}
              />
            </div>

            <p className="text-[11px] text-muted mt-2 tabular-nums leading-relaxed">
              {formatBytes(uploadBatchStats.processedBytes)} de{" "}
              {formatBytes(uploadBatchStats.totalBytes)} · {uploadBatchStats.overallProgress}%
              {uploadBatchStats.avgSpeed > 0 && (
                <> · média {formatSpeed(uploadBatchStats.avgSpeed)}</>
              )}
              {uploadBatchStats.etaSec !== null && !uploadBatchFinished && (
                <> · ~{formatDuration(uploadBatchStats.etaSec)} restante</>
              )}
              <> · {formatDuration(uploadBatchStats.elapsedSec)} decorrido</>
            </p>
          </div>

          {uploadPanelExpanded && (
            <div className="max-h-72 overflow-y-auto border-t border-[var(--glass-border)]/60">
              {uploads.map((job) => {
                const elapsedSec = (Date.now() - job.startedAt) / 1000;
                const etaSec = estimateRemainingSeconds(elapsedSec, job.progress);

                return (
                  <div
                    key={uploadJobKey(job)}
                    className="px-4 py-2.5 border-b border-[var(--glass-border)]/40 last:border-b-0"
                  >
                    <div className="flex justify-between items-center gap-2 mb-1">
                      <span className="truncate text-xs font-medium text-[var(--text-primary)]">
                        {uploadDisplayName(job)}
                      </span>
                      <div className="flex items-center gap-1 shrink-0">
                        {!isUploadTerminal(job.phase) && (
                          <button
                            type="button"
                            onClick={() => cancelUploadFile(job)}
                            className="w-5 h-5 flex items-center justify-center rounded hover:bg-[var(--bg-base)] text-muted hover:text-[var(--danger)] transition-colors text-sm leading-none"
                            aria-label={`Cancelar upload de ${uploadDisplayName(job)}`}
                          >
                            ×
                          </button>
                        )}
                        <span
                          className={`text-[11px] tabular-nums ${
                            job.phase === "error"
                              ? "text-[var(--danger)]"
                              : job.phase === "cancelled"
                                ? "text-[var(--warning)]"
                                : job.phase === "done"
                                  ? "text-emerald-500"
                                  : "text-[var(--accent)]"
                          }`}
                        >
                          {job.phase === "error"
                            ? "Erro"
                            : job.phase === "cancelled"
                              ? "Cancelado"
                              : job.phase === "done"
                                ? "OK"
                                : `${job.progress}%`}
                        </span>
                      </div>
                    </div>
                    <div className="h-1 rounded-full bg-[var(--bg-base)] overflow-hidden mb-1">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${
                          job.phase === "error"
                            ? "bg-[var(--danger)]"
                            : job.phase === "cancelled"
                              ? "bg-[var(--warning)]"
                              : job.phase === "done"
                                ? "bg-emerald-500"
                                : "bg-[var(--accent)]"
                        }`}
                        style={{
                          width: `${
                            job.phase === "cancelled" ? 100 : job.progress
                          }%`,
                        }}
                      />
                    </div>
                    <p className="text-[10px] text-muted truncate">
                      {job.phase === "error" ? (
                        job.error ?? "Falha no upload"
                      ) : job.phase === "cancelled" ? (
                        "Upload cancelado"
                      ) : (
                        <>
                          {uploadPhaseLabel(job.phase)} · {formatBytes(job.file.size)}
                          {job.phase !== "done" && job.speedBps > 0 && (
                            <> · {formatSpeed(job.speedBps)}</>
                          )}
                          {etaSec !== null && job.phase !== "done" && (
                            <> · ~{formatDuration(etaSec)}</>
                          )}
                        </>
                      )}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {downloadJob && (
        <div
          className="fixed bottom-4 left-4 z-40 w-[min(calc(100vw-2rem),24rem)] glass-card shadow-2xl border border-[var(--glass-border)] overflow-hidden"
          role="region"
          aria-label="Progresso de download"
        >
          <div className="px-4 py-3 bg-[var(--bg-elevated)]/80 backdrop-blur-sm">
            {(() => {
              void downloadTick;
              const elapsedSec = (Date.now() - downloadJob.startedAt) / 1000;
              const total = downloadJob.totalBytes ?? downloadJob.sizeBytes;
              const title =
                downloadJob.phase === "done"
                  ? "Download concluído"
                  : downloadJob.phase === "cancelled"
                    ? "Download cancelado"
                    : downloadJob.phase === "error"
                      ? "Falha no download"
                      : downloadJob.phase === "saving"
                        ? "Escolha onde salvar…"
                        : downloadJob.phase === "preparing"
                          ? "Preparando arquivo…"
                          : "Baixando…";

              return (
                <>
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-[var(--text-primary)] truncate">
                        {title}
                      </p>
                      <p className="text-xs text-muted mt-0.5 truncate">{downloadJob.name}</p>
                    </div>
                    {!downloadFinished && (
                      <button
                        type="button"
                        onClick={cancelDownloadTransfer}
                        className="w-7 h-7 flex items-center justify-center shrink-0 rounded-lg hover:bg-[var(--bg-base)] text-muted hover:text-[var(--danger)] transition-colors text-lg leading-none"
                        aria-label="Cancelar download"
                      >
                        ×
                      </button>
                    )}
                  </div>

                  <div className="mt-2.5 h-2 rounded-full bg-[var(--bg-base)] overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-300 ${
                        downloadJob.phase === "error"
                          ? "bg-[var(--danger)]"
                          : downloadJob.phase === "cancelled"
                            ? "bg-[var(--warning)]"
                            : downloadJob.phase === "done"
                              ? "bg-emerald-500"
                              : downloadJob.phase === "saving"
                                ? "bg-[var(--accent)] animate-pulse"
                                : "bg-gradient-to-r from-brand-500 to-[var(--accent)]"
                      }`}
                      style={{
                        width: `${
                          downloadJob.phase === "preparing" && downloadJob.progress === 0
                            ? 30
                            : downloadJob.progress
                        }%`,
                      }}
                    />
                  </div>

                  <p className="text-[11px] text-muted mt-2 tabular-nums leading-relaxed">
                    {downloadJob.phase === "error" ? (
                      <span className="text-[var(--danger)]">{downloadJob.error}</span>
                    ) : downloadJob.phase === "saving" ? (
                      <>
                        Transferência pronta — selecione a pasta e o nome do arquivo no diálogo do
                        sistema
                      </>
                    ) : downloadJob.phase === "done" ? (
                      <>Arquivo salvo · {formatDuration(elapsedSec)}</>
                    ) : downloadJob.phase === "cancelled" ? (
                      <>Download cancelado · {formatDuration(elapsedSec)}</>
                    ) : (
                      <>
                        {formatBytes(downloadJob.loadedBytes)}
                        {total > 0 && <> de {formatBytes(total)}</>}
                        {" · "}
                        {downloadJob.progress}%
                        {" · "}
                        {formatDuration(elapsedSec)}
                        {downloadJob.phase === "preparing" && <> · preparando arquivo</>}
                      </>
                    )}
                  </p>
                </>
              );
            })()}
          </div>
        </div>
      )}
      <PixPaymentModal
        open={pixOpen && pendingPix != null}
        onClose={() => setPixOpen(false)}
        brCode={pendingPix?.brCode ?? null}
        qrBase64={pendingPix?.qrBase64 ?? null}
        amountCents={pendingPix?.amountCents}
        expiresAt={pendingPix?.expiresAt}
        refreshing={pixRefreshing}
        onRefresh={async () => {
          if (!pendingPix) return;
          setPixRefreshing(true);
          try {
            const sync = await api.cloudStorageSyncPayment(pendingPix.orderId);
            setPendingPix({
              orderId: pendingPix.orderId,
              brCode: sync.pix_br_code ?? pendingPix.brCode,
              qrBase64: sync.pix_qr_base64 ?? pendingPix.qrBase64,
              expiresAt: sync.pix_expires_at ?? pendingPix.expiresAt,
              amountCents: sync.total_cents || pendingPix.amountCents,
            });
            setPixOpen(true);
          } finally {
            setPixRefreshing(false);
          }
        }}
      />
      {pendingPix && !pixOpen && (
        <div className="fixed bottom-5 inset-x-0 z-40 flex justify-center px-4 pointer-events-none">
          <div className="pointer-events-auto w-full max-w-md">
            <PixPayButton onClick={() => setPixOpen(true)} label="Mostrar QR Code Pix" />
          </div>
        </div>
      )}
    </div>
  );
}
