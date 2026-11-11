import { SvgSpinner } from "@/components/ui/svgs";

type Props = {
  label?: string;
  compact?: boolean;
  framed?: boolean;
};

export function PageLoader({
  label = "Carregando…",
  compact = false,
  framed = true,
}: Props) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-4 px-6 ${
        compact ? "py-14 min-h-[14rem]" : "py-20 min-h-[22rem]"
      } ${framed ? "glass-card rounded-2xl" : ""}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <SvgSpinner className="w-11 h-11 text-[var(--accent)]" />
      <p className="text-sm text-muted">{label}</p>
    </div>
  );
}

export function InlineLoader({ label = "Carregando…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 text-sm text-muted py-1" role="status" aria-live="polite">
      <SvgSpinner className="w-5 h-5 text-[var(--accent)]" />
      <span>{label}</span>
    </div>
  );
}

export function BusyLabel({ children = "Processando…" }: { children?: string }) {
  return (
    <span className="inline-flex items-center justify-center gap-2">
      <SvgSpinner className="w-4 h-4" />
      {children}
    </span>
  );
}
