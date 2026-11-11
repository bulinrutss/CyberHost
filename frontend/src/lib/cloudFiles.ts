/** Fallback alinhado ao teto HTTP do proxy (768 KiB). Preferir quota.chunk_size_bytes da API. */
export const DEFAULT_CHUNK_SIZE_BYTES = 768 * 1024;
/** Fallback mínimo; o limite real vem da API ou NEXT_PUBLIC_CLOUD_MAX_UPLOAD_GB. */
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

const STALE_UPLOAD_CAP_BYTES = 2147483648; // 2 GB — valor de backends antigos

export function envMaxUploadBytes(): number {
  const raw = process.env.NEXT_PUBLIC_CLOUD_MAX_UPLOAD_GB;
  if (!raw) return 0;
  const gb = Number(raw);
  if (!Number.isFinite(gb) || gb <= 0) return 0;
  return Math.floor(gb * 1024 ** 3);
}

/** Escolhe o maior limite confiável (ignora teto stale de 2 GB quando há valor maior). */
export function resolveMaxUploadBytes(...candidates: Array<number | null | undefined>): number {
  const envLimit = envMaxUploadBytes();
  const valid = candidates.filter((n): n is number => typeof n === "number" && n > 0);
  const bestApi = valid.length ? Math.max(...valid) : 0;

  if (bestApi > STALE_UPLOAD_CAP_BYTES) return bestApi;
  if (envLimit > bestApi) return envLimit;
  if (bestApi > 0) return bestApi;
  if (envLimit > 0) return envLimit;
  return MAX_UPLOAD_BYTES;
}
export const MAX_CONCURRENT_UPLOADS = 5;

export function chunkCount(sizeBytes: number, chunkSizeBytes = DEFAULT_CHUNK_SIZE_BYTES): number {
  return Math.max(1, Math.ceil(sizeBytes / chunkSizeBytes));
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** i;
  return `${value.toFixed(i === 0 ? 0 : value < 10 ? 1 : 0)} ${units[i]}`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fileExtension(name: string): string {
  const base = name.split("/").pop() ?? name;
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(dot + 1).toLowerCase() : "";
}

export async function readFileChunk(
  file: File,
  index: number,
  chunkSizeBytes = DEFAULT_CHUNK_SIZE_BYTES
): Promise<Blob> {
  const start = index * chunkSizeBytes;
  const end = Math.min(start + chunkSizeBytes, file.size);
  return file.slice(start, end);
}

export type UploadPipelinePhase =
  | "pending"
  | "uploading"
  | "syncing"
  | "finalizing"
  | "done"
  | "cancelled"
  | "error";

/** Bytes já processados com base na contagem de fragmentos. */
export function bytesFromChunkProgress(
  fileSize: number,
  chunksDone: number,
  totalChunks: number,
  chunkSizeBytes = DEFAULT_CHUNK_SIZE_BYTES
): number {
  if (chunksDone <= 0) return 0;
  if (chunksDone >= totalChunks) return fileSize;
  return chunksDone * chunkSizeBytes;
}

/** Pesos de cada etapa do pipeline (somam 100). */
const UPLOAD_PROGRESS_WEIGHT = 50;
const SYNC_PROGRESS_WEIGHT = 45;
const FINALIZE_PROGRESS = 97;

/** Progresso 0–100 do pipeline completo (servidor + Discord + finalização). */
export function computePipelineProgress(
  chunksDone: number,
  syncDone: number,
  totalChunks: number,
  phase: UploadPipelinePhase
): number {
  if (phase === "done") return 100;
  if (phase === "error" || phase === "cancelled") return 0;

  const total = Math.max(1, totalChunks);
  const uploadRatio = Math.min(1, chunksDone / total);
  const syncRatio = Math.min(1, syncDone / total);

  if (phase === "finalizing") return FINALIZE_PROGRESS;

  if (phase === "syncing") {
    return Math.min(
      FINALIZE_PROGRESS - 1,
      Math.round(UPLOAD_PROGRESS_WEIGHT + syncRatio * SYNC_PROGRESS_WEIGHT)
    );
  }

  if (phase === "uploading" || phase === "pending") {
    return Math.round(uploadRatio * UPLOAD_PROGRESS_WEIGHT);
  }

  return Math.min(
    FINALIZE_PROGRESS - 1,
    Math.round(UPLOAD_PROGRESS_WEIGHT * uploadRatio + SYNC_PROGRESS_WEIGHT * syncRatio)
  );
}

export function uploadPhaseLabel(phase: UploadPipelinePhase): string {
  switch (phase) {
    case "pending":
      return "Na fila";
    case "uploading":
      return "Enviando";
    case "syncing":
      return "Processando";
    case "finalizing":
      return "Finalizando";
    case "done":
      return "Disponível";
    case "cancelled":
      return "Cancelado";
    case "error":
      return "Erro";
  }
}

export function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "—";
  const s = Math.round(totalSeconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return r > 0 ? `${m}m ${r}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`;
}

export function formatSpeed(bytesPerSecond: number): string {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return "—";
  return `${formatBytes(bytesPerSecond)}/s`;
}

export function estimateRemainingSeconds(
  elapsedSec: number,
  progressPercent: number
): number | null {
  if (progressPercent < 3 || progressPercent >= 100) return null;
  return (elapsedSec / progressPercent) * (100 - progressPercent);
}

export function smoothSpeed(prevBps: number, instantBps: number): number {
  if (instantBps <= 0) return prevBps > 0 ? prevBps * 0.9 : 0;
  if (prevBps <= 0) return instantBps;
  return prevBps * 0.6 + instantBps * 0.4;
}

export type FileUploadEntry = {
  file: File;
  /** Caminho relativo incluindo subpastas, ex.: `Projeto/src/main.ts`. */
  relativePath: string | null;
};

export type UploadTask = FileUploadEntry & {
  targetParentId: number | null;
};

export function fileRelativePath(file: File): string | null {
  const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath?.trim();
  return rel || null;
}

export function parseRelativePath(relativePath: string): { dirParts: string[]; fileName: string } {
  const parts = relativePath.split("/").filter(Boolean);
  const fileName = parts.pop() ?? relativePath;
  return { dirParts: parts, fileName };
}

export function uploadEntryKey(entry: Pick<FileUploadEntry, "file" | "relativePath">): string {
  const path = entry.relativePath ?? fileRelativePath(entry.file) ?? "";
  return `${path}::${entry.file.name}::${entry.file.size}::${entry.file.lastModified}`;
}

export function uploadDisplayName(entry: Pick<FileUploadEntry, "file" | "relativePath">): string {
  return entry.relativePath ?? fileRelativePath(entry.file) ?? entry.file.name;
}

export function partitionFilesByMaxSize(
  files: File[],
  maxBytes: number
): { valid: File[]; oversize: File[] } {
  const valid: File[] = [];
  const oversize: File[] = [];
  for (const file of files) {
    if (file.size > maxBytes) oversize.push(file);
    else valid.push(file);
  }
  return { valid, oversize };
}

export function collectFilesFromFileList(fileList: FileList | File[]): FileUploadEntry[] {
  return Array.from(fileList).map((file) => ({
    file,
    relativePath: fileRelativePath(file),
  }));
}

async function readDirectoryEntries(
  reader: FileSystemDirectoryReader,
  dirPath: string,
  out: FileUploadEntry[]
): Promise<void> {
  const readBatch = (): Promise<FileSystemEntry[]> =>
    new Promise((resolve, reject) => reader.readEntries(resolve, reject));

  let batch: FileSystemEntry[];
  do {
    batch = await readBatch();
    for (const entry of batch) {
      await traverseFileSystemEntry(entry, dirPath, out);
    }
  } while (batch.length > 0);
}

async function traverseFileSystemEntry(
  entry: FileSystemEntry,
  parentPath: string,
  out: FileUploadEntry[]
): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => {
      (entry as FileSystemFileEntry).file(resolve, reject);
    });
    const relativePath = parentPath ? `${parentPath}/${file.name}` : file.name;
    out.push({ file, relativePath });
    return;
  }

  if (!entry.isDirectory) return;

  const dirPath = parentPath ? `${parentPath}/${entry.name}` : entry.name;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  await readDirectoryEntries(reader, dirPath, out);
}

/** Coleta arquivos de um drop (pastas ou arquivos soltos). */
export async function collectFilesFromDataTransfer(
  dataTransfer: DataTransfer
): Promise<FileUploadEntry[]> {
  const items = dataTransfer.items;
  if (!items?.length) {
    return collectFilesFromFileList(dataTransfer.files);
  }

  const entries: FileUploadEntry[] = [];
  const tasks: Promise<void>[] = [];

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.kind !== "file") continue;

    const entry = item.webkitGetAsEntry?.();
    if (entry) {
      tasks.push(traverseFileSystemEntry(entry, "", entries));
      continue;
    }

    const file = item.getAsFile();
    if (file) {
      entries.push({ file, relativePath: fileRelativePath(file) });
    }
  }

  if (tasks.length) await Promise.all(tasks);
  if (entries.length) return entries;

  return collectFilesFromFileList(dataTransfer.files);
}

/** Limite para visualizar texto no navegador (evita travar com arquivos enormes). */
export const TEXT_PREVIEW_MAX_BYTES = 512 * 1024;

const TEXT_EXTENSIONS = new Set([
  "txt",
  "md",
  "markdown",
  "json",
  "xml",
  "html",
  "htm",
  "css",
  "js",
  "mjs",
  "cjs",
  "ts",
  "tsx",
  "jsx",
  "py",
  "log",
  "csv",
  "yaml",
  "yml",
  "ini",
  "env",
  "conf",
  "config",
  "sh",
  "bat",
  "cmd",
  "ps1",
  "sql",
  "toml",
  "properties",
  "gitignore",
  "dockerfile",
  "nginx",
  "htaccess",
]);

const TEXT_MIME_PREFIXES = ["text/"];
const TEXT_MIME_EXACT = new Set([
  "application/json",
  "application/xml",
  "application/javascript",
  "application/x-javascript",
  "application/sql",
  "application/yaml",
  "application/x-yaml",
  "application/toml",
  "application/x-sh",
  "application/x-bat",
  "application/x-httpd-php",
  "image/svg+xml",
]);

export function isTextFile(item: { name: string; mime_type: string | null }): boolean {
  const mime = (item.mime_type ?? "").toLowerCase().split(";")[0].trim();
  if (mime && TEXT_MIME_PREFIXES.some((p) => mime.startsWith(p))) return true;
  if (mime && TEXT_MIME_EXACT.has(mime)) return true;

  const ext = fileExtension(item.name);
  if (ext && TEXT_EXTENSIONS.has(ext)) return true;
  if (item.name.toLowerCase() === "dockerfile") return true;
  if (item.name.startsWith(".") && item.name.length > 1) return true;
  return false;
}

export function canPreviewTextFile(item: {
  name: string;
  mime_type: string | null;
  size_bytes: number;
  is_folder?: boolean;
  upload_status?: string;
}): boolean {
  if (item.is_folder || item.upload_status !== "ready") return false;
  if (!isTextFile(item)) return false;
  return item.size_bytes <= TEXT_PREVIEW_MAX_BYTES;
}

export function textPreviewLimitLabel(): string {
  return formatBytes(TEXT_PREVIEW_MAX_BYTES);
}
