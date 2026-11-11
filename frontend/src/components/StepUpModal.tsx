"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  cancelStepUpPrompt,
  completeStepUpPrompt,
  subscribeStepUp,
} from "@/lib/stepUp";
import { BusyLabel } from "@/components/PageLoader";

export function StepUpModal() {
  const [open, setOpen] = useState(false);
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    return subscribeStepUp((nextOpen, nextMfa) => {
      setOpen(nextOpen);
      setMfaEnabled(nextMfa);
      if (nextOpen) {
        setPassword("");
        setMfaCode("");
        setError("");
        setBusy(false);
      }
    });
  }, []);

  if (!open) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.stepUp(password, mfaEnabled ? mfaCode : undefined);
      completeStepUpPrompt(res.step_up_token, res.expires_in);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível confirmar");
      setBusy(false);
    }
  };

  const cancel = () => {
    if (busy) return;
    cancelStepUpPrompt();
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/45 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="step-up-title"
    >
      <form
        onSubmit={submit}
        className="glass-card w-full max-w-md p-6 shadow-xl border border-[var(--glass-border)]"
      >
        <h2 id="step-up-title" className="text-lg font-semibold mb-1">
          Confirmar identidade
        </h2>
        <p className="text-sm text-muted mb-5">
          Esta ação é sensível. Digite a senha da conta
          {mfaEnabled ? " e o código MFA" : ""} para continuar. A confirmação vale por
          alguns minutos.
        </p>

        <label className="block text-xs text-muted mb-1.5">Senha de acesso</label>
        <input
          type="password"
          autoComplete="current-password"
          className="input-glass mb-3"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
          autoFocus
          required
        />

        {mfaEnabled && (
          <>
            <label className="block text-xs text-muted mb-1.5">Código MFA</label>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              className="input-glass mb-3 font-mono tracking-widest"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value.replace(/\s/g, ""))}
              disabled={busy}
              placeholder="000000"
              required
            />
          </>
        )}

        {error && (
          <p className="text-sm text-[var(--danger)] mb-3 rounded-lg px-3 py-2 bg-[var(--danger)]/10 border border-[var(--danger)]/25">
            {error}
          </p>
        )}

        <div className="flex flex-wrap gap-2 justify-end mt-2">
          <button type="button" className="btn-ghost" onClick={cancel} disabled={busy}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary" disabled={busy || !password}>
            {busy ? <BusyLabel>Confirmando…</BusyLabel> : "Confirmar"}
          </button>
        </div>
      </form>
    </div>
  );
}
