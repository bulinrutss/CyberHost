"use client";

import { useEffect } from "react";
import type { LegalSection } from "@/lib/legal";

type Props = {
  open: boolean;
  title: string;
  updatedAt: string;
  sections: LegalSection[];
  onClose: () => void;
};

export function LegalModal({ open, title, updatedAt, sections, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  const titleId = `legal-modal-${title.toLowerCase().replace(/\s+/g, "-")}`;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="glass-card w-full max-w-2xl max-h-[85vh] flex flex-col p-6 sm:p-8 relative"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-3 right-3 w-9 h-9 rounded-lg text-muted hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
          aria-label="Fechar"
        >
          ×
        </button>

        <p className="text-sm text-[var(--accent)] uppercase tracking-wide mb-1">CyberHost</p>
        <h2 id={titleId} className="text-xl font-bold pr-10">
          {title}
        </h2>
        <p className="text-xs text-[var(--text-muted)] mt-1 mb-4">Atualizado em {updatedAt}</p>

        <div className="overflow-y-auto pr-1 space-y-5 text-sm text-[var(--text-secondary)] leading-relaxed">
          {sections.map((section) => (
            <section key={section.title}>
              <h3 className="font-semibold text-[var(--text-primary)] mb-2">{section.title}</h3>
              {section.paragraphs.map((paragraph, index) => (
                <p key={`${section.title}-${index}`} className="mb-2 last:mb-0">
                  {paragraph}
                </p>
              ))}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
