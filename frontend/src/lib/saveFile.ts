/** Salva blob no disco — tenta diálogo "Salvar como" (File System Access API). */
export async function saveFileAfterDownload(
  blob: Blob,
  filename: string,
  mimeType?: string | null
): Promise<"saved" | "cancelled"> {
  if (typeof window !== "undefined" && "showSaveFilePicker" in window) {
    try {
      const pickerOpts: {
        suggestedName: string;
        types?: Array<{ description: string; accept: Record<string, string[]> }>;
      } = {
        suggestedName: filename,
      };
      if (mimeType) {
        pickerOpts.types = [
          {
            description: "Arquivo",
            accept: { [mimeType]: [guessExtension(filename)] },
          },
        ];
      }
      const handle = await (window.showSaveFilePicker as (opts: unknown) => Promise<FileSystemFileHandle>)(pickerOpts);
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return "saved";
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        return "cancelled";
      }
    }
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
  return "saved";
}

function guessExtension(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(dot) : ".*";
}
