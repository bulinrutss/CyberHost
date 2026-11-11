"use client";

import type { ReactNode } from "react";
import { SvgChevronDown } from "@/components/ui/svgs";

type Props = {
  title: string;
  summary?: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
};

export function ExpandableSection({ title, summary, open, onToggle, children }: Props) {
  return (
    <div className="glass-card overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 p-5 text-left hover:bg-[var(--bg-elevated)]/40 transition"
      >
        <div className="min-w-0">
          <p className="font-medium">{title}</p>
          {summary ? <p className="text-xs text-muted truncate mt-0.5">{summary}</p> : null}
        </div>
        <SvgChevronDown
          className={`w-4 h-4 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open ? (
        <div className="px-5 pb-5 border-t border-[var(--glass-border)] pt-4">{children}</div>
      ) : null}
    </div>
  );
}
