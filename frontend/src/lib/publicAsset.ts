/** Caminho de arquivo em public/, respeitando NEXT_PUBLIC_BASE_PATH em produção. */
export function publicAsset(path: string): string {
  const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalized}`;
}
