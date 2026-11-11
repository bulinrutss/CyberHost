"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { normalizePhoneInput } from "@/lib/phone";
import { BusyLabel } from "@/components/PageLoader";

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated: (message: string) => void;
  onError: (message: string) => void;
};

export function AdminCreateClientModal({ open, onClose, onCreated, onError }: Props) {
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    if (!open) return;
    setPhone("");
    setEmail("");
    setName("");
    setPassword("");
    setIsAdmin(false);
    setLocalError("");
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, busy, onClose]);

  if (!open) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError("");
    setBusy(true);
    try {
      const user = await api.adminCreateUser({
        phone: normalizePhoneInput(phone),
        email: email.trim(),
        name: name.trim(),
        password,
        is_admin: isAdmin,
      });
      onCreated(`Conta de ${user.name} criada`);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Não foi possível cadastrar";
      setLocalError(msg);
      onError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60"
      onClick={() => {
        if (!busy) onClose();
      }}
      role="presentation"
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-client-title"
        className="glass-card w-full max-w-md p-6"
        onClick={(event) => event.stopPropagation()}
        onSubmit={submit}
      >
        <h2 id="create-client-title" className="text-lg font-bold mb-1">
          Cadastrar novo cliente
        </h2>
        <p className="text-sm text-secondary mb-4">
          Cadastro completo com e-mail para login, avisos e cobrança.
        </p>
        <div className="space-y-3">
          <input
            type="text"
            required
            minLength={2}
            placeholder="Nome"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="input-glass"
          />
          <input
            type="email"
            required
            placeholder="E-mail"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input-glass"
          />
          <input
            type="tel"
            required
            inputMode="numeric"
            placeholder="Telefone"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="input-glass"
          />
          <input
            type="password"
            required
            minLength={8}
            placeholder="Senha (mín. 8)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input-glass"
          />
          <label className="flex items-center gap-2 text-sm text-secondary">
            <input
              type="checkbox"
              checked={isAdmin}
              onChange={(e) => setIsAdmin(e.target.checked)}
            />
            Administrador
          </label>
        </div>
        {localError ? <p className="text-sm text-red-400 mt-3">{localError}</p> : null}
        <div className="flex gap-2 mt-5">
          <button type="button" className="btn-ghost flex-1" disabled={busy} onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary flex-1" disabled={busy}>
            {busy ? <BusyLabel>Cadastrando…</BusyLabel> : "Criar conta"}
          </button>
        </div>
      </form>
    </div>
  );
}
