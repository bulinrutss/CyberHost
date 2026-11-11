"use client";

import { useEffect, useMemo, useState } from "react";
import { formatPrice } from "@/lib/api";
import { BusyLabel } from "@/components/PageLoader";

export type PixPaymentDetails = {
  brCode: string | null;
  qrBase64: string | null;
  amountCents?: number | null;
  expiresAt?: string | null;
};

type Props = PixPaymentDetails & {
  open: boolean;
  onClose: () => void;
  onRefresh?: () => void | Promise<void>;
  refreshing?: boolean;
  title?: string;
};

export function pixIsExpired(expiresAt?: string | null): boolean {
  if (!expiresAt) return false;
  const ts = Date.parse(expiresAt);
  return Number.isFinite(ts) && ts <= Date.now();
}

export function qrImageSrc(qrBase64: string | null | undefined): string | null {
  if (!qrBase64) return null;
  if (qrBase64.startsWith("data:")) return qrBase64;
  return `data:image/png;base64,${qrBase64}`;
}

function remainingLabel(expiresAt: string | null | undefined): string | null {
  if (!expiresAt) return null;
  const ts = Date.parse(expiresAt);
  if (!Number.isFinite(ts)) return null;
  const ms = ts - Date.now();
  if (ms <= 0) return "Expirado";
  const totalSec = Math.floor(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${String(sec).padStart(2, "0")}`;
}

export function PixPayButton({
  onClick,
  label = "Mostrar QR Code Pix",
}: {
  onClick: () => void;
  label?: string;
}) {
  return (
    <button type="button" onClick={onClick} className="btn-primary w-full !py-3">
      {label}
    </button>
  );
}

export function PixPaymentModal({
  open,
  onClose,
  onRefresh,
  refreshing = false,
  brCode,
  qrBase64,
  amountCents,
  expiresAt,
  title = "Pague com Pix",
}: Props) {
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(Date.now());
  const expired = pixIsExpired(expiresAt);
  const qrSrc = qrImageSrc(qrBase64);
  const remaining = useMemo(() => remainingLabel(expiresAt), [expiresAt, now]);

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

  useEffect(() => {
    if (!open || !expiresAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [open, expiresAt]);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  if (!open) return null;

  const copyCode = async () => {
    if (!brCode) return;
    try {
      await navigator.clipboard.writeText(brCode);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="pix-modal-title"
        className="glass-card w-full max-w-md p-6 sm:p-8 relative"
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

        <p className="text-sm text-[var(--accent)] uppercase tracking-wide mb-1">Pagamento</p>
        <h2 id="pix-modal-title" className="text-xl font-bold mb-1">
          {title}
        </h2>
        <p className="text-secondary text-sm mb-5">
          Escaneie o QR Code no app do banco ou copie o código. A confirmação é automática.
        </p>

        {typeof amountCents === "number" && amountCents > 0 && (
          <p className="text-2xl font-bold text-center mb-4">{formatPrice(amountCents)}</p>
        )}

        {expired ? (
          <div className="rounded-xl border border-[var(--warning)]/30 bg-[var(--warning)]/10 p-4 text-center mb-4">
            <p className="text-sm text-[var(--warning)] mb-3">Este QR Code expirou.</p>
            {onRefresh && (
              <button
                type="button"
                onClick={() => void onRefresh()}
                disabled={refreshing}
                className="btn-primary"
              >
                {refreshing ? <BusyLabel>Gerando…</BusyLabel> : "Gerar novo QR Code"}
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="mx-auto mb-4 w-fit rounded-2xl bg-white p-3 shadow-sm">
              {qrSrc ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={qrSrc} alt="QR Code Pix" className="w-52 h-52 sm:w-56 sm:h-56" />
              ) : (
                <div className="w-52 h-52 sm:w-56 sm:h-56 flex items-center justify-center text-sm text-slate-500">
                  QR indisponível — use o copia e cola
                </div>
              )}
            </div>

            {remaining && (
              <p className="text-center text-xs text-muted mb-3">
                Expira em <span className="tabular-nums font-semibold text-secondary">{remaining}</span>
              </p>
            )}

            <p className="text-xs text-muted mb-2">Pix copia e cola</p>
            <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] p-3 mb-3">
              <p className="text-[11px] font-mono break-all leading-relaxed text-secondary">
                {brCode || "Aguardando código…"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void copyCode()}
              disabled={!brCode}
              className="btn-primary w-full !py-3 mb-3"
            >
              {copied ? "Código copiado" : "Copiar código Pix"}
            </button>
          </>
        )}

        <p className="text-center text-xs text-muted">
          Pode fechar esta janela — o QR continua disponível nesta página.
        </p>
      </div>
    </div>
  );
}
