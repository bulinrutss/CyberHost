import type { FinanceKind } from "@/lib/api";
import { formatPrice } from "@/lib/api";

export function todayISODate(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

export function addDays(date: Date, n: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return startOfDay(d);
}

export function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function getWeekDaysFor(date: Date): Date[] {
  const d = startOfDay(date);
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

export function formatMonthYear(date: Date): string {
  const s = date.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function formatDayLetter(date: Date): string {
  return date.toLocaleDateString("pt-BR", { weekday: "narrow" }).replace(".", "").toUpperCase();
}

export function formatWeekday(date: Date): string {
  return date.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function parseBRLToCents(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const normalized = trimmed.replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
  const n = Number(normalized);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.round(n * 100);
}

export function centsToInput(cents: number): string {
  return (cents / 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function transactionLabel(title: string, fallback: string): string {
  const trimmed = title.trim();
  return trimmed || fallback;
}

export function signedPrice(cents: number, kind?: FinanceKind): string {
  const value = kind === "expense" ? -Math.abs(cents) : kind === "income" ? Math.abs(cents) : cents;
  const formatted = formatPrice(Math.abs(value));
  if (value < 0) return `− ${formatted}`;
  if (value > 0 && kind === "income") return `+ ${formatted}`;
  return formatted;
}

export function toLocalDateTime(date: string, time: string): string {
  return `${date}T${time}:00`;
}

export function splitDateTime(iso: string): { date: string; time: string } {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return { date: todayISODate(d), time: `${hh}:${mm}` };
}

export type FinancePeriodId = "month" | "7d" | "30d" | "year" | "all" | "custom";

export function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

export function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

export function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

export function periodBounds(
  id: FinancePeriodId,
  monthCursor: Date,
  customStart: string,
  customEnd: string
): { start?: string; end?: string; label: string } {
  const today = startOfDay(new Date());
  if (id === "month") {
    const start = startOfMonth(monthCursor);
    const end = endOfMonth(monthCursor);
    return { start: todayISODate(start), end: todayISODate(end), label: formatMonthYear(start) };
  }
  if (id === "7d") {
    return {
      start: todayISODate(addDays(today, -6)),
      end: todayISODate(today),
      label: "Últimos 7 dias",
    };
  }
  if (id === "30d") {
    return {
      start: todayISODate(addDays(today, -29)),
      end: todayISODate(today),
      label: "Últimos 30 dias",
    };
  }
  if (id === "year") {
    const start = new Date(today.getFullYear(), 0, 1);
    return { start: todayISODate(start), end: todayISODate(today), label: `Ano ${today.getFullYear()}` };
  }
  if (id === "custom") {
    return {
      start: customStart || undefined,
      end: customEnd || undefined,
      label: "Período personalizado",
    };
  }
  return { label: "Todo o período" };
}
