export function normalizeSearch(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function matchesAdminQuery(
  query: string,
  parts: Array<string | number | null | undefined>
): boolean {
  const raw = query.trim();
  if (!raw) return true;
  const needle = normalizeSearch(raw);
  const needleDigits = raw.replace(/\D/g, "");
  return parts.some((part) => {
    if (part == null || part === "") return false;
    const text = String(part);
    if (normalizeSearch(text).includes(needle)) return true;
    if (needleDigits.length >= 3) {
      const digits = text.replace(/\D/g, "");
      if (digits.includes(needleDigits)) return true;
    }
    return false;
  });
}
