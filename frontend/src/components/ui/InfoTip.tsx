"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { SvgInfo } from "@/components/ui/svgs";

type Props = {
  children: ReactNode;
  label?: string;
  align?: "start" | "end";
};

export function InfoTip({ children, label = "Como funciona", align = "start" }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const tooltipId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={rootRef} className="relative inline-flex align-middle">
      <button
        type="button"
        className="inline-flex items-center justify-center w-5 h-5 rounded-full shrink-0 text-muted hover:text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors"
        aria-label={label}
        aria-expanded={open}
        aria-controls={tooltipId}
        onClick={() => setOpen((value) => !value)}
      >
        <SvgInfo className="w-4 h-4" />
      </button>
      {open && (
        <span
          id={tooltipId}
          role="tooltip"
          className={`absolute top-full z-50 mt-2 w-64 max-w-[min(16rem,calc(100vw-2rem))] rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] px-3 py-2.5 text-xs leading-relaxed text-secondary shadow-lg ${
            align === "end" ? "right-0" : "left-0"
          }`}
        >
          {children}
        </span>
      )}
    </span>
  );
}
