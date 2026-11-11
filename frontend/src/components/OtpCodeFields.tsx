"use client";

import { useEffect, useState } from "react";
import { BusyLabel } from "@/components/PageLoader";

type Props = {
  target: string;
  required: boolean;
  canSend?: boolean;
  hint: string;
  sendLabel: string;
  resendLabel: string;
  codeLabel: string;
  code: string;
  onCodeChange: (value: string) => void;
  onTicket: (ticket: string) => void;
  send: (target: string) => Promise<{ ticket: string; retry_after: number }>;
  disabled?: boolean;
};

export function OtpCodeFields({
  target,
  required,
  canSend = true,
  hint,
  sendLabel,
  resendLabel,
  codeLabel,
  code,
  onCodeChange,
  onTicket,
  send,
  disabled,
}: Props) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);

  useEffect(() => {
    if (retryAfter <= 0) return;
    const timer = window.setTimeout(() => setRetryAfter((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [retryAfter]);

  if (!required) return null;

  const sendCode = async () => {
    setError("");
    setSending(true);
    try {
      const result = await send(target);
      onTicket(result.ticket);
      setSent(true);
      setRetryAfter(result.retry_after);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível enviar o código");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted leading-relaxed">{hint}</p>
      <button
        type="button"
        disabled={disabled || sending || retryAfter > 0 || !canSend}
        onClick={sendCode}
        className="btn-ghost w-full !py-2.5"
      >
        {sending ? (
          <BusyLabel>Enviando…</BusyLabel>
        ) : retryAfter > 0 ? (
          `Reenviar em ${retryAfter}s`
        ) : sent ? (
          resendLabel
        ) : (
          sendLabel
        )}
      </button>
      {sent && (
        <div>
          <label className="text-xs text-muted block mb-1.5">{codeLabel}</label>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            minLength={6}
            maxLength={8}
            className="input-glass tracking-[0.3em] text-center text-lg"
            placeholder="000000"
            value={code}
            onChange={(e) => onCodeChange(e.target.value.replace(/\D/g, "").slice(0, 8))}
          />
        </div>
      )}
      {error && (
        <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-2">
          {error}
        </p>
      )}
    </div>
  );
}
