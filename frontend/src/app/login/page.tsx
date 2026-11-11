"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { CyberHostLogo } from "@/components/CyberHostLogo";
import { PageShell } from "@/components/ui/PageShell";
import { api, setToken, type LoginResult } from "@/lib/api";
import { loginWithPasskey } from "@/components/AccountSecurityPanel";
import { BusyLabel } from "@/components/PageLoader";

type Step = "credentials" | "mfa" | "setup";

export default function LoginPage() {
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<Step>("credentials");
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
    setToken();
    const user = await api.me();
    router.push(user.is_admin ? "/admin" : "/dashboard");
  };

  const submitPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api.login(phone, password);
      await finish(result);
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
      const result = await api.verifyMfa(ticket, code.replace(/\s/g, ""));
      await finish(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código MFA inválido");
    } finally {
      setLoading(false);
    }
  };

  const secretDisplay = mfaSecret.replace(/(.{4})/g, "$1 ").trim();

  return (
    <PageShell>
      <div className="max-w-md mx-auto">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-6">
            <CyberHostLogo href="/" height={42} />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">
            {step === "credentials" ? "Acesse sua conta" : "Verificação em dois passos"}
          </h1>
          <p className="text-secondary mt-2">
            {step === "setup"
              ? "Cadastre o autenticador para concluir o acesso"
              : step === "mfa"
                ? "Digite o código de 6 dígitos do autenticador"
                : "Entre no painel CyberHost"}
          </p>
        </div>

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
            {error && (
              <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 border border-[var(--danger)]/20 rounded-xl px-4 py-2">
                {error}
              </p>
            )}
            <button type="submit" disabled={loading} className="btn-primary w-full !py-3">
              {loading ? <BusyLabel>Entrando…</BusyLabel> : "Entrar"}
            </button>
            <button
              type="button"
              disabled={loading || !phone.trim()}
              className="btn-ghost w-full !py-3"
              onClick={() => {
                void (async () => {
                  setLoading(true);
                  setError("");
                  try {
                    const result = await loginWithPasskey(phone.trim());
                    await finish(result);
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Falha no login com passkey");
                  } finally {
                    setLoading(false);
                  }
                })();
              }}
            >
              Entrar com passkey
            </button>
          </form>
        ) : (
          <form onSubmit={submitMfa} className="glass-card p-8 space-y-5">
            {step === "setup" && (
              <div className="space-y-3 text-sm">
                <p className="text-secondary">
                  Adicione esta chave no Google Authenticator, Aegis ou similar. Depois digite o
                  código gerado.
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
            {error && (
              <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 border border-[var(--danger)]/20 rounded-xl px-4 py-2">
                {error}
              </p>
            )}
            <button type="submit" disabled={loading} className="btn-primary w-full !py-3">
              {loading ? <BusyLabel>Verificando…</BusyLabel> : "Confirmar"}
            </button>
            <button
              type="button"
              className="btn-ghost w-full !py-2 text-sm"
              onClick={() => {
                setStep("credentials");
                setCode("");
                setTicket("");
                setMfaSecret("");
                setError("");
              }}
            >
              Voltar
            </button>
          </form>
        )}

        {step === "credentials" && (
          <p className="text-center text-muted mt-6 text-sm">
            Sem conta?{" "}
            <Link href="/register" className="text-[var(--accent)] hover:underline font-medium">
              Criar conta
            </Link>
          </p>
        )}
      </div>
    </PageShell>
  );
}
