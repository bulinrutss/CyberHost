"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AuthSessionItem,
  type PasskeyItem,
  type User,
} from "@/lib/api";
import { BusyLabel } from "@/components/PageLoader";

function bufferToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let str = "";
  bytes.forEach((b) => {
    str += String.fromCharCode(b);
  });
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlToBuffer(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
  const binary = atob(padded + pad);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function publicKeyFromJson(options: Record<string, unknown>): PublicKeyCredentialCreationOptions {
  const exclude = (options.excludeCredentials as Array<Record<string, unknown>> | undefined)?.map(
    (item) => ({
      ...item,
      id: base64urlToBuffer(String(item.id)),
      type: "public-key" as const,
    })
  );
  return {
    ...(options as object),
    challenge: base64urlToBuffer(String(options.challenge)),
    user: {
      ...(options.user as object),
      id: base64urlToBuffer(String((options.user as { id: string }).id)),
    },
    excludeCredentials: exclude,
  } as PublicKeyCredentialCreationOptions;
}

function requestFromJson(options: Record<string, unknown>): PublicKeyCredentialRequestOptions {
  const allow = (options.allowCredentials as Array<Record<string, unknown>> | undefined)?.map(
    (item) => ({
      ...item,
      id: base64urlToBuffer(String(item.id)),
      type: "public-key" as const,
    })
  );
  return {
    ...(options as object),
    challenge: base64urlToBuffer(String(options.challenge)),
    allowCredentials: allow,
  } as PublicKeyCredentialRequestOptions;
}

function credentialToJson(cred: PublicKeyCredential): Record<string, unknown> {
  const response = cred.response as AuthenticatorAttestationResponse | AuthenticatorAssertionResponse;
  const base: Record<string, unknown> = {
    id: cred.id,
    rawId: bufferToBase64url(cred.rawId),
    type: cred.type,
    response: {},
    clientExtensionResults: cred.getClientExtensionResults(),
  };
  if ("attestationObject" in response) {
    base.response = {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
      transports:
        typeof response.getTransports === "function" ? response.getTransports() : undefined,
    };
  } else {
    base.response = {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
    };
  }
  return base;
}

type Props = {
  user: User;
  onUserChange: (user: User) => void;
};

export function AccountSecurityPanel({ user, onUserChange }: Props) {
  const [sessions, setSessions] = useState<AuthSessionItem[]>([]);
  const [passkeys, setPasskeys] = useState<PasskeyItem[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  const [mfaPassword, setMfaPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaTicket, setMfaTicket] = useState("");
  const [mfaSecret, setMfaSecret] = useState("");
  const [otpauthUrl, setOtpauthUrl] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [passkeyName, setPasskeyName] = useState("Este dispositivo");

  const load = useCallback(async () => {
    const [s, p] = await Promise.all([api.authSessions(), api.listPasskeys()]);
    setSessions(s);
    setPasskeys(p);
  }, []);

  useEffect(() => {
    void load().catch(() => undefined);
  }, [load]);

  const flash = (ok: string) => {
    setMessage(ok);
    setError("");
  };

  const startMfa = async () => {
    setBusy("mfa-start");
    setError("");
    try {
      const result = await api.mfaSetupStart(mfaPassword);
      setMfaTicket(result.mfa_ticket);
      setMfaSecret(result.mfa_secret);
      setOtpauthUrl(result.otpauth_url);
      flash("Escaneie o QR/código no autenticador e confirme com o código de 6 dígitos.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar MFA");
    } finally {
      setBusy("");
    }
  };

  const confirmMfa = async () => {
    setBusy("mfa-confirm");
    setError("");
    try {
      const updated = await api.mfaSetupConfirm(mfaTicket, mfaCode.replace(/\s/g, ""));
      onUserChange(updated);
      setMfaPassword("");
      setMfaCode("");
      setMfaTicket("");
      setMfaSecret("");
      setOtpauthUrl("");
      flash("MFA ativado. No próximo login será pedido o código.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código inválido");
    } finally {
      setBusy("");
    }
  };

  const disableMfa = async () => {
    setBusy("mfa-disable");
    setError("");
    try {
      const updated = await api.mfaDisable(disablePassword, disableCode.replace(/\s/g, ""));
      onUserChange(updated);
      setDisablePassword("");
      setDisableCode("");
      flash("MFA desativado.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível desativar MFA");
    } finally {
      setBusy("");
    }
  };

  const addPasskey = async () => {
    if (!window.PublicKeyCredential) {
      setError("Este navegador não suporta passkeys.");
      return;
    }
    setBusy("passkey-add");
    setError("");
    try {
      const options = (await api.passkeyRegisterOptions()) as Record<string, unknown>;
      const cred = (await navigator.credentials.create({
        publicKey: publicKeyFromJson(options),
      })) as PublicKeyCredential | null;
      if (!cred) throw new Error("Passkey cancelada");
      await api.passkeyRegisterVerify(credentialToJson(cred), passkeyName.trim() || "Passkey");
      await load();
      flash("Passkey cadastrada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao cadastrar passkey");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-6 max-w-xl">
      {error && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-400">
          {error}
        </div>
      )}
      {message && (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-400">
          {message}
        </div>
      )}

      <section className="glass-card p-6 space-y-4">
        <div>
          <h2 className="font-semibold text-lg">Autenticação em dois fatores (MFA)</h2>
          <p className="text-sm text-muted mt-1">
            Opcional. Use um app autenticador (Google Authenticator, Authy, etc.).
          </p>
        </div>
        {user.mfa_enabled ? (
          <div className="space-y-3">
            <p className="text-sm text-emerald-400">MFA ativo nesta conta.</p>
            <input
              type="password"
              className="input-glass"
              placeholder="Senha atual"
              value={disablePassword}
              onChange={(e) => setDisablePassword(e.target.value)}
            />
            <input
              type="text"
              inputMode="numeric"
              className="input-glass"
              placeholder="Código de 6 dígitos"
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value)}
            />
            <button
              type="button"
              className="btn-ghost !py-2 text-red-300"
              disabled={!!busy}
              onClick={() => void disableMfa()}
            >
              {busy === "mfa-disable" ? <BusyLabel>Desativando…</BusyLabel> : "Desativar MFA"}
            </button>
          </div>
        ) : !mfaTicket ? (
          <div className="space-y-3">
            <input
              type="password"
              className="input-glass"
              placeholder="Senha atual para ativar"
              value={mfaPassword}
              onChange={(e) => setMfaPassword(e.target.value)}
            />
            <button
              type="button"
              className="btn-primary !py-2"
              disabled={!!busy || !mfaPassword}
              onClick={() => void startMfa()}
            >
              {busy === "mfa-start" ? <BusyLabel>Gerando…</BusyLabel> : "Ativar MFA"}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-secondary break-all">
              Segredo: <span className="font-mono">{mfaSecret}</span>
            </p>
            {otpauthUrl && (
              <a href={otpauthUrl} className="text-sm text-[var(--accent)] hover:underline">
                Abrir no autenticador
              </a>
            )}
            <input
              type="text"
              inputMode="numeric"
              className="input-glass"
              placeholder="Código de 6 dígitos"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
            />
            <button
              type="button"
              className="btn-primary !py-2"
              disabled={!!busy || mfaCode.length < 6}
              onClick={() => void confirmMfa()}
            >
              {busy === "mfa-confirm" ? <BusyLabel>Confirmando…</BusyLabel> : "Confirmar MFA"}
            </button>
          </div>
        )}
      </section>

      <section className="glass-card p-6 space-y-4">
        <div>
          <h2 className="font-semibold text-lg">Passkeys</h2>
          <p className="text-sm text-muted mt-1">
            Login com biometria / Windows Hello / chave de segurança — sem senha.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            className="input-glass flex-1"
            value={passkeyName}
            onChange={(e) => setPasskeyName(e.target.value)}
            placeholder="Nome do dispositivo"
          />
          <button
            type="button"
            className="btn-primary !py-2"
            disabled={!!busy}
            onClick={() => void addPasskey()}
          >
            {busy === "passkey-add" ? <BusyLabel>Aguardando…</BusyLabel> : "Adicionar passkey"}
          </button>
        </div>
        {!passkeys.length ? (
          <p className="text-sm text-muted">Nenhuma passkey cadastrada.</p>
        ) : (
          <ul className="space-y-2">
            {passkeys.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 text-sm border border-[var(--glass-border)] rounded-xl px-3 py-2"
              >
                <div>
                  <p className="font-medium">{item.device_name}</p>
                  <p className="text-xs text-muted">
                    Criada {new Date(item.created_at).toLocaleString("pt-BR")}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn-ghost !py-1 !px-2 text-xs text-red-300"
                  onClick={() =>
                    void api
                      .deletePasskey(item.id)
                      .then(load)
                      .then(() => flash("Passkey removida."))
                      .catch((err) =>
                        setError(err instanceof Error ? err.message : "Erro ao remover")
                      )
                  }
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="glass-card p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold text-lg">Sessões ativas</h2>
            <p className="text-sm text-muted mt-1">Revogue acessos em outros dispositivos.</p>
          </div>
          <button
            type="button"
            className="btn-ghost !py-1.5 text-sm"
            onClick={() =>
              void api
                .revokeOtherAuthSessions()
                .then(load)
                .then(() => flash("Outras sessões encerradas."))
                .catch((err) =>
                  setError(err instanceof Error ? err.message : "Erro ao revogar")
                )
            }
          >
            Encerrar outras
          </button>
        </div>
        {!sessions.length ? (
          <p className="text-sm text-muted">Nenhuma sessão listada.</p>
        ) : (
          <ul className="space-y-2">
            {sessions.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 text-sm border border-[var(--glass-border)] rounded-xl px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="font-medium truncate">
                    {item.current ? "Este dispositivo" : item.ip || "Sessão"}
                    {item.current ? (
                      <span className="ml-2 text-[10px] uppercase text-[var(--accent)]">atual</span>
                    ) : null}
                  </p>
                  <p className="text-xs text-muted truncate">{item.user_agent || "—"}</p>
                  <p className="text-[10px] text-muted">
                    Visto {new Date(item.last_seen_at).toLocaleString("pt-BR")}
                  </p>
                </div>
                {!item.current && (
                  <button
                    type="button"
                    className="btn-ghost !py-1 !px-2 text-xs text-red-300 shrink-0"
                    onClick={() =>
                      void api
                        .revokeAuthSession(item.id)
                        .then(load)
                        .then(() => flash("Sessão encerrada."))
                        .catch((err) =>
                          setError(err instanceof Error ? err.message : "Erro ao revogar")
                        )
                    }
                  >
                    Encerrar
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export async function loginWithPasskey(username: string) {
  if (!window.PublicKeyCredential) {
    throw new Error("Este navegador não suporta passkeys");
  }
  const options = (await api.passkeyLoginOptions(username)) as Record<string, unknown>;
  const cred = (await navigator.credentials.get({
    publicKey: requestFromJson(options),
  })) as PublicKeyCredential | null;
  if (!cred) throw new Error("Passkey cancelada");
  return api.passkeyLoginVerify(username, credentialToJson(cred));
}
