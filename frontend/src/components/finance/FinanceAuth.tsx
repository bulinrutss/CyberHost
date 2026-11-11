"use client";

import { useState } from "react";
import { BusyLabel } from "@/components/PageLoader";
import { api, type LoginResult } from "@/lib/api";
import { setFinanceToken } from "@/lib/financeSession";
import { normalizePhoneInput } from "@/lib/phone";

type Mode = "login" | "register";
type LoginStep = "credentials" | "mfa" | "setup";

export function FinanceAuth({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<Mode>("login");
  return (
    <div className="max-w-md mx-auto">
      <div className="text-center mb-8">
        <p className="text-xs font-semibold tracking-[0.2em] uppercase text-[var(--accent)] mb-3">
          ruts.dev/financeiro
        </p>
        <h1 className="text-3xl font-bold tracking-tight">
          {mode === "login" ? "Acesse sua conta" : "Criar conta"}
        </h1>
        <p className="text-secondary mt-2">
          {mode === "login"
            ? "Entre para ver agenda, gastos e entradas"
            : "Cadastre nome, e-mail, celular e senha para começar"}
        </p>
      </div>
      {mode === "login" ? (
        <LoginForm onDone={onDone} onSwitch={() => setMode("register")} />
      ) : (
        <RegisterForm onDone={onDone} onSwitch={() => setMode("login")} />
      )}
    </div>
  );
}

function LoginForm({ onDone, onSwitch }: { onDone: () => void; onSwitch: () => void }) {
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<LoginStep>("credentials");
  const [ticket, setTicket] = useState("");
  const [mfaSecret, setMfaSecret] = useState("");
  const [otpauthUrl, setOtpauthUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const finish = async (result: LoginResult) => {
    if (result.mfa_setup_required && result.mfa_ticket) {
      setTicket(result.mfa_ticket);
      setMfaSecret(result.mfa_secret || "");
      setOtpauthUrl(result.otpauth_url || "");
      setStep("setup");
      setCode("");
      return;
    }
    if (result.mfa_required && result.mfa_ticket) {
      setTicket(result.mfa_ticket);
      setStep("mfa");
      setCode("");
      return;
    }
    if (!result.authenticated) {
      throw new Error("Resposta de login incompleta");
    }
    setFinanceToken();
    onDone();
  };

  const submitPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await finish(await api.financeLogin(phone, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Telefone, e-mail ou senha incorretos");
    } finally {
      setLoading(false);
    }
  };

  const submitMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await finish(await api.financeVerifyMfa(ticket, code.replace(/\s/g, "")));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código MFA inválido");
    } finally {
      setLoading(false);
    }
  };

  const secretDisplay = mfaSecret.replace(/(.{4})/g, "$1 ").trim();

  return (
    <>
      {step === "credentials" ? (
        <form onSubmit={submitPassword} className="glass-card p-8 space-y-5">
          <div>
            <label className="text-xs text-muted block mb-1.5">Telefone ou e-mail</label>
            <input
              type="text"
              required
              autoComplete="username"
              placeholder="(11) 99999-9999 ou e-mail"
              className="input-glass"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-muted block mb-1.5">Senha</label>
            <input
              type="password"
              required
              className="input-glass"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <ErrorBox>{error}</ErrorBox>}
          <button type="submit" disabled={loading} className="btn-primary w-full !py-3">
            {loading ? <BusyLabel>Entrando…</BusyLabel> : "Entrar"}
          </button>
        </form>
      ) : (
        <form onSubmit={submitMfa} className="glass-card p-8 space-y-5">
          {step === "setup" && (
            <div className="space-y-3 text-sm">
              <p className="text-secondary">
                Adicione esta chave no autenticador e digite o código gerado.
              </p>
              <p className="font-mono text-lg tracking-widest break-all bg-[var(--bg-elevated)] rounded-xl px-4 py-3">
                {secretDisplay}
              </p>
              {otpauthUrl && (
                <a href={otpauthUrl} className="text-[var(--accent)] hover:underline font-medium">
                  Abrir no aplicativo autenticador
                </a>
              )}
            </div>
          )}
          <div>
            <label className="text-xs text-muted block mb-1.5">Código de 6 dígitos</label>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              minLength={6}
              maxLength={8}
              className="input-glass tracking-[0.4em] text-center text-lg"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
            />
          </div>
          {error && <ErrorBox>{error}</ErrorBox>}
          <button type="submit" disabled={loading} className="btn-primary w-full !py-3">
            {loading ? <BusyLabel>Verificando…</BusyLabel> : "Confirmar"}
          </button>
        </form>
      )}
      {step === "credentials" && (
        <p className="text-center text-muted mt-6 text-sm">
          Sem conta?{" "}
          <button type="button" onClick={onSwitch} className="text-[var(--accent)] hover:underline font-medium">
            Criar conta
          </button>
        </p>
      )}
    </>
  );
}

function RegisterForm({ onDone, onSwitch }: { onDone: () => void; onSwitch: () => void }) {
  const [form, setForm] = useState({ phone: "", email: "", name: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const phone = normalizePhoneInput(form.phone);
      await api.financeRegister({ ...form, phone });
      const result = await api.financeLogin(phone, form.password);
      if (!result.authenticated) {
        throw new Error("Conta criada. Faça login para continuar.");
      }
      setFinanceToken();
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao registrar");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <form onSubmit={submit} className="glass-card p-8 space-y-5">
        <div>
          <label className="text-xs text-muted block mb-1.5">Nome</label>
          <input
            type="text"
            required
            className="input-glass"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs text-muted block mb-1.5">E-mail</label>
          <input
            type="email"
            required
            autoComplete="email"
            placeholder="voce@email.com"
            className="input-glass"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs text-muted block mb-1.5">Celular</label>
          <input
            type="tel"
            required
            inputMode="numeric"
            placeholder="(11) 99999-9999"
            className="input-glass"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs text-muted block mb-1.5">Senha</label>
          <input
            type="password"
            required
            minLength={8}
            className="input-glass"
            placeholder="Mín. 8 caracteres"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </div>
        {error && <ErrorBox>{error}</ErrorBox>}
        <button type="submit" disabled={loading} className="btn-primary w-full !py-3">
          {loading ? <BusyLabel>Criando…</BusyLabel> : "Criar conta"}
        </button>
      </form>
      <p className="text-center text-muted mt-6 text-sm">
        Já tem conta?{" "}
        <button type="button" onClick={onSwitch} className="text-[var(--accent)] hover:underline font-medium">
          Entrar
        </button>
      </p>
    </>
  );
}

function ErrorBox({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 border border-[var(--danger)]/20 rounded-xl px-4 py-2">
      {children}
    </p>
  );
}
