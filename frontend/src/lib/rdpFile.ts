/** Gera um .rdp que o Remote Desktop do Windows (mstsc) abre. */

function rdpField(value: string): string {
  return value.replace(/[\r\n]/g, "").trim();
}

export function buildRdpFileContents(address: string, username: string): string {
  const host = rdpField(address);
  const user = rdpField(username);
  return [
    `full address:s:${host}`,
    `username:s:${user}`,
    "prompt for credentials:i:1",
    "authentication level:i:2",
    "negotiate security layer:i:1",
    "enablecredsspsupport:i:1",
    "autoreconnection enabled:i:1",
    "networkautodetect:i:1",
    "redirectclipboard:i:1",
  ].join("\r\n") + "\r\n";
}

function utf16leWithBom(text: string): Uint8Array {
  const out = new Uint8Array(2 + text.length * 2);
  out[0] = 0xff;
  out[1] = 0xfe;
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    out[2 + i * 2] = code & 0xff;
    out[3 + i * 2] = code >> 8;
  }
  return out;
}

export function rdpFilename(vmName?: string): string {
  const base = (vmName || "vps").replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  return `${base || "vps"}.rdp`;
}

export function downloadRdpFile(address: string, username: string, vmName?: string): void {
  const bytes = utf16leWithBom(buildRdpFileContents(address, username));
  const copy = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(copy).set(bytes);
  const blob = new Blob([copy], { type: "application/rdp" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = rdpFilename(vmName);
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}
