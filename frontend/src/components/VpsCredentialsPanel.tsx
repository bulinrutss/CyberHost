"use client";

import { useState } from "react";
import { SvgMonitor } from "@/components/ui/svgs";
import { InfoTip } from "@/components/ui/InfoTip";
import { downloadRdpFile } from "@/lib/rdpFile";
import { api } from "@/lib/api";

type Props = {
  instanceId: number;
  rdpConnectionAddress?: string | null;
  osLabel?: string | null;
  vmName?: string;
  username: string;
  password?: string | null;
  hasPassword?: boolean;
  compact?: boolean;
  admin?: boolean;
};

export function VpsCredentialsPanel({
  instanceId,
  rdpConnectionAddress,
  osLabel,
  vmName,
  username,
  password: initialPassword = null,
  hasPassword = false,
  compact = false,
  admin = false,
}: Props) {
  const [revealed, setRevealed] = useState(false);
  const [password, setPassword] = useState(initialPassword || "");
  const [loadingSecret, setLoadingSecret] = useState(false);
  const [secretError, setSecretError] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  const rdpTarget = rdpConnectionAddress?.trim() || "";
  const canReveal = Boolean(password) || hasPassword || Boolean(initialPassword);

  const copy = async (label: string, value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      /* ignore */
    }
  };

  const ensurePassword = async (): Promise<string | null> => {
    if (password) return password;
    setLoadingSecret(true);
    setSecretError("");
    try {
      const creds = admin
        ? await api.adminInstanceCredentials(instanceId)
        : await api.instanceCredentials(instanceId);
      const next = creds.password || "";
      setPassword(next);
      return next || null;
    } catch (e) {
      setSecretError(e instanceof Error ? e.message : "Não foi possível revelar a senha");
      return null;
    } finally {
      setLoadingSecret(false);
    }
  };

  const toggleReveal = async () => {
    if (revealed) {
      setRevealed(false);
      return;
    }
    const secret = await ensurePassword();
    if (secret) setRevealed(true);
  };

  const copyPassword = async () => {
    const secret = await ensurePassword();
    if (secret) void copy("pass", secret);
  };

  const copyAll = async () => {
    const secret = await ensurePassword();
    if (!secret) return;
    const lines = [
      vmName ? `Servidor: ${vmName}` : null,
      rdpTarget ? `Endereço: ${rdpTarget}` : null,
      `Usuário: ${username}`,
      `Senha: ${secret}`,
    ].filter(Boolean);
    void copy("all", lines.join("\n"));
  };

  const openRdp = () => {
    if (!rdpTarget) return;
    downloadRdpFile(rdpTarget, username, vmName);
  };

  const fieldBtn = (label: string, onClick: () => void, disabled = false) => (
    <button
      type="button"
      className="btn-ghost !py-0.5 !px-2 text-[11px] shrink-0"
      onClick={onClick}
      disabled={disabled}
    >
      {copied === label ? "OK" : "Copiar"}
    </button>
  );

  return (
    <div className="glass-card w-full p-3 sm:p-4 border border-[var(--accent)]/20">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-[var(--accent)]/10 flex items-center justify-center shrink-0">
            <SvgMonitor className="w-4 h-4 text-[var(--accent)]" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-tight inline-flex items-center gap-1.5">
              {compact ? "Conexão" : "Acesso RDP"}
              <InfoTip align="end">
                Use o endereço público, o usuário e a senha para entrar no Windows.
                Ver / copiar a senha pede confirmação da conta. Abrir .rdp baixa um
                arquivo para o Remote Desktop.
              </InfoTip>
            </p>
            {osLabel && <p className="text-[11px] text-muted truncate">{osLabel}</p>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void copyAll()}
            className="btn-ghost !py-1 !px-2.5 text-xs"
            disabled={!canReveal || loadingSecret}
          >
            {copied === "all" ? "Copiado" : "Copiar tudo"}
          </button>
          {rdpTarget && (
            <button type="button" onClick={openRdp} className="btn-primary !py-1 !px-2.5 text-xs">
              Abrir .rdp
            </button>
          )}
        </div>
      </div>

      {secretError && (
        <p className="text-xs text-[var(--danger)] mb-2">{secretError}</p>
      )}

      <div className={compact ? "grid grid-cols-1 gap-2" : "grid grid-cols-1 sm:grid-cols-3 gap-2"}>
        <div className="rounded-lg border border-[var(--glass-border)]/60 bg-[var(--bg-elevated)]/50 px-3 py-2">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <p className="text-[10px] text-muted uppercase tracking-wide">Endereço</p>
            {rdpTarget && fieldBtn("host", () => copy("host", rdpTarget))}
          </div>
          {rdpTarget ? (
            <p className="font-mono text-sm font-semibold text-[var(--accent)] break-all leading-tight">
              {rdpTarget}
            </p>
          ) : (
            <p className="text-xs text-muted">Endereço pendente</p>
          )}
        </div>

        <div className="rounded-lg border border-[var(--glass-border)]/60 bg-[var(--bg-elevated)]/50 px-3 py-2">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <p className="text-[10px] text-muted uppercase tracking-wide">Usuário</p>
            {fieldBtn("user", () => copy("user", username))}
          </div>
          <p className="font-mono text-sm font-medium break-all leading-tight">{username}</p>
        </div>

        <div className="rounded-lg border border-[var(--glass-border)]/60 bg-[var(--bg-elevated)]/50 px-3 py-2">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <p className="text-[10px] text-muted uppercase tracking-wide">Senha</p>
            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                className="btn-ghost !py-0.5 !px-2 text-[11px]"
                onClick={() => void toggleReveal()}
                disabled={!canReveal || loadingSecret}
              >
                {loadingSecret ? "…" : revealed ? "Ocultar" : "Ver"}
              </button>
              {fieldBtn("pass", () => void copyPassword(), !canReveal || loadingSecret)}
            </div>
          </div>
          <p className="font-mono text-sm font-medium break-all leading-tight">
            {revealed && password ? password : "••••••••••••"}
          </p>
        </div>
      </div>
    </div>
  );
}
