"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { OtpCodeFields } from "@/components/OtpCodeFields";
import { PageShell } from "@/components/ui/PageShell";
import { WhatsAppOtpFields } from "@/components/WhatsAppOtpFields";
import { api, getToken, type User } from "@/lib/api";
import { normalizePhoneInput } from "@/lib/phone";
import { AccountSecurityPanel } from "@/components/AccountSecurityPanel";
import { BusyLabel, PageLoader } from "@/components/PageLoader";

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [whatsappRequired, setWhatsappRequired] = useState(false);
  const [whatsappTicket, setWhatsappTicket] = useState("");
  const [whatsappCode, setWhatsappCode] = useState("");
  const [emailRequired, setEmailRequired] = useState(false);
  const [emailTicket, setEmailTicket] = useState("");
  const [emailCode, setEmailCode] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api
      .phoneVerification()
      .then((status) => setWhatsappRequired(status.required))
      .catch(() => setWhatsappRequired(false));
    api
      .emailVerification()
      .then((status) => setEmailRequired(status.required))
      .catch(() => setEmailRequired(false));
    api
      .me()
      .then((me) => {
        setUser(me);
        setName(me.name);
        setEmail(me.email || "");
        setPhone(me.phone);
      })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    if (newPassword && newPassword !== confirmPassword) {
      setError("A nova senha e a confirmação não conferem.");
      return;
    }
    setSaving(true);
    try {
      if (!user) {
        setSaving(false);
        return;
      }
      const nextPhone = normalizePhoneInput(phone);
      const phoneChanged = nextPhone !== normalizePhoneInput(user.phone);
      if (whatsappRequired && phoneChanged && (!whatsappTicket || whatsappCode.length < 6)) {
        setError("Confirme o novo telefone com o código enviado no WhatsApp.");
        setSaving(false);
        return;
      }
      const nextEmail = email.trim().toLowerCase();
      const emailChanged = nextEmail !== (user.email || "").toLowerCase();
      if (emailRequired && emailChanged && (!emailTicket || emailCode.length < 6)) {
        setError("Confirme o novo e-mail com o código enviado.");
        setSaving(false);
        return;
      }
      const updated = await api.updateProfile({
        name: name.trim(),
        email: nextEmail,
        phone: nextPhone,
        current_password: currentPassword,
        ...(newPassword ? { new_password: newPassword } : {}),
        ...(whatsappRequired && phoneChanged
          ? { whatsapp_ticket: whatsappTicket, whatsapp_code: whatsappCode }
          : {}),
        ...(emailRequired && emailChanged
          ? { email_ticket: emailTicket, email_code: emailCode }
          : {}),
      });
      setUser(updated);
      setName(updated.name);
      setEmail(updated.email || "");
      setPhone(updated.phone);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setWhatsappTicket("");
      setWhatsappCode("");
      setEmailTicket("");
      setEmailCode("");
      setMessage("Perfil atualizado.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível salvar o perfil");
    } finally {
      setSaving(false);
    }
  };

  if (loading || !user) {
    return (
      <PageShell wide>
        <PageLoader label="Carregando perfil…" />
      </PageShell>
    );
  }

  return (
    <PageShell admin={user.is_admin} wide>
      <p className="text-sm font-medium text-[var(--accent)] mb-2 tracking-wide uppercase">
        Minha conta
      </p>
      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">Perfil</h1>
      <p className="text-secondary mb-8 max-w-lg">
        Atualize nome, e-mail, telefone e senha. Confirme com a senha atual para salvar.
      </p>

      <form onSubmit={submit} className="glass-card p-6 sm:p-8 max-w-xl space-y-5">
        <div>
          <label className="text-xs text-muted block mb-1.5">Nome</label>
          <input
            type="text"
            required
            minLength={2}
            maxLength={120}
            autoComplete="name"
            className="input-glass"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label className="text-xs text-muted block mb-1.5">E-mail</label>
          <input
            type="email"
            required
            autoComplete="email"
            className="input-glass"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setEmailTicket("");
              setEmailCode("");
            }}
          />
        </div>
        {user && emailRequired && email.trim().toLowerCase() !== (user.email || "").toLowerCase() && (
          <OtpCodeFields
            key={email.trim().toLowerCase()}
            target={email.trim()}
            required
            canSend={email.includes("@")}
            hint="Enviaremos um código para o novo e-mail."
            sendLabel="Enviar código no e-mail"
            resendLabel="Reenviar código no e-mail"
            codeLabel="Código do e-mail"
            code={emailCode}
            onCodeChange={setEmailCode}
            onTicket={setEmailTicket}
            send={api.sendEmailCodeProfile}
          />
        )}
        <div>
          <label className="text-xs text-muted block mb-1.5">Telefone</label>
          <input
            type="tel"
            required
            inputMode="numeric"
            autoComplete="tel"
            placeholder="(11) 99999-9999"
            className="input-glass"
            value={phone}
            onChange={(e) => {
              setPhone(e.target.value);
              setWhatsappTicket("");
              setWhatsappCode("");
            }}
          />
        </div>
        {user && whatsappRequired && normalizePhoneInput(phone) !== normalizePhoneInput(user.phone) && (
          <WhatsAppOtpFields
            key={normalizePhoneInput(phone)}
            phone={phone}
            required
            code={whatsappCode}
            onCodeChange={setWhatsappCode}
            onTicket={setWhatsappTicket}
            send={api.sendWhatsAppCodeProfile}
          />
        )}
        <div>
          <label className="text-xs text-muted block mb-1.5">Senha atual</label>
          <input
            type="password"
            required
            autoComplete="current-password"
            className="input-glass"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-muted block mb-1.5">Nova senha (opcional)</label>
            <input
              type="password"
              minLength={8}
              autoComplete="new-password"
              placeholder="Mín. 8 caracteres"
              className="input-glass"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-muted block mb-1.5">Confirmar nova senha</label>
            <input
              type="password"
              minLength={8}
              required={!!newPassword}
              autoComplete="new-password"
              className="input-glass"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>
        </div>
        {error && (
          <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 border border-[var(--danger)]/20 rounded-xl px-4 py-2">
            {error}
          </p>
        )}
        {message && (
          <p className="text-sm text-green-400 bg-green-400/10 border border-green-800 rounded-xl px-4 py-2">
            {message}
          </p>
        )}
        <button type="submit" disabled={saving} className="btn-primary !py-3">
          {saving ? <BusyLabel>Salvando…</BusyLabel> : "Salvar alterações"}
        </button>
      </form>

      <div className="mt-10">
        <h2 className="text-2xl font-bold tracking-tight mb-2">Segurança</h2>
        <p className="text-secondary mb-6 max-w-lg">
          MFA opcional, passkeys e sessões ativas neste dispositivo e em outros.
        </p>
        <AccountSecurityPanel user={user} onUserChange={setUser} />
      </div>
    </PageShell>
  );
}
