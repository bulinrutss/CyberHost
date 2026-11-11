"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { CyberHostLogo } from "@/components/CyberHostLogo";
import { OtpCodeFields } from "@/components/OtpCodeFields";
import { PageShell } from "@/components/ui/PageShell";
import { WhatsAppOtpFields } from "@/components/WhatsAppOtpFields";
import { api, setToken } from "@/lib/api";
import { normalizePhoneInput } from "@/lib/phone";
import { BusyLabel } from "@/components/PageLoader";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ phone: "", email: "", name: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [whatsappRequired, setWhatsappRequired] = useState(false);
  const [whatsappOptIn, setWhatsappOptIn] = useState(false);
  const [whatsappTicket, setWhatsappTicket] = useState("");
  const [whatsappCode, setWhatsappCode] = useState("");
  const [emailRequired, setEmailRequired] = useState(false);
  const [emailTicket, setEmailTicket] = useState("");
  const [emailCode, setEmailCode] = useState("");

  useEffect(() => {
    api
      .phoneVerification()
      .then((status) => setWhatsappRequired(status.required))
      .catch(() => setWhatsappRequired(false));
    api
      .emailVerification()
      .then((status) => setEmailRequired(status.required))
      .catch(() => setEmailRequired(false));
  }, []);

  useEffect(() => {
    setWhatsappTicket("");
    setWhatsappCode("");
  }, [form.phone]);

  useEffect(() => {
    setEmailTicket("");
    setEmailCode("");
  }, [form.email]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const phone = normalizePhoneInput(form.phone);
      if (whatsappRequired && !whatsappOptIn) {
        throw new Error("Aceite receber o código no WhatsApp para continuar.");
      }
      if (whatsappRequired && (!whatsappTicket || whatsappCode.length < 6)) {
        throw new Error("Envie e informe o código recebido no WhatsApp.");
      }
      if (emailRequired && (!emailTicket || emailCode.length < 6)) {
        throw new Error("Envie e informe o código recebido no e-mail.");
      }
      await api.register({
        ...form,
        phone,
        ...(whatsappRequired
          ? { whatsapp_ticket: whatsappTicket, whatsapp_code: whatsappCode }
          : {}),
        ...(emailRequired ? { email_ticket: emailTicket, email_code: emailCode } : {}),
      });
      const result = await api.login(phone, form.password);
      if (!result.authenticated) {
        throw new Error("Conta criada. Faça login para continuar.");
      }
      setToken();
      router.push("/order");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao registrar");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageShell>
      <div className="max-w-md mx-auto">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-6">
            <CyberHostLogo href="/" height={42} />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Criar conta</h1>
          <p className="text-secondary mt-2">Cadastre-se e ganhe 20 GB no CyberCloud + provisione sua VPS em minutos</p>
        </div>

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
            <label className="text-xs text-muted block mb-1.5">Telefone</label>
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
          {whatsappRequired && (
            <label className="flex items-start gap-3 text-sm text-secondary">
              <input
                type="checkbox"
                className="mt-1"
                checked={whatsappOptIn}
                onChange={(e) => setWhatsappOptIn(e.target.checked)}
              />
              <span>
                Concordo em receber um código de verificação da CyberHost no WhatsApp no número informado.
              </span>
            </label>
          )}
          <WhatsAppOtpFields
            key={normalizePhoneInput(form.phone)}
            phone={form.phone}
            required={whatsappRequired}
            code={whatsappCode}
            onCodeChange={setWhatsappCode}
            onTicket={setWhatsappTicket}
            send={api.sendWhatsAppCode}
            disabled={!whatsappOptIn}
          />
          <OtpCodeFields
            key={form.email.trim().toLowerCase()}
            target={form.email.trim()}
            required={emailRequired}
            canSend={form.email.includes("@")}
            hint="Enviaremos um código para este e-mail. Confira também a pasta de spam."
            sendLabel="Enviar código no e-mail"
            resendLabel="Reenviar código no e-mail"
            codeLabel="Código do e-mail"
            code={emailCode}
            onCodeChange={setEmailCode}
            onTicket={setEmailTicket}
            send={api.sendEmailCode}
          />
          {error && (
            <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-2">
              {error}
            </p>
          )}
          <button type="submit" disabled={loading} className="btn-primary w-full !py-3">
            {loading ? <BusyLabel>Criando…</BusyLabel> : "Criar conta"}
          </button>
        </form>

        <p className="text-center text-muted mt-6 text-sm">
          Já tem conta?{" "}
          <Link href="/login" className="text-[var(--accent)] hover:underline font-medium">
            Entrar
          </Link>
        </p>
      </div>
    </PageShell>
  );
}
