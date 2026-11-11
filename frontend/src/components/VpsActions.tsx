"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { PowerStateBadge } from "@/components/PowerStateBadge";
import { ProvisionProgress } from "@/components/ProvisionProgress";
import type { VpsInstanceDetail } from "@/lib/api";
import { VpsCredentialsPanel } from "@/components/VpsCredentialsPanel";
import { BusyLabel } from "@/components/PageLoader";
import { InfoTip } from "@/components/ui/InfoTip";

type ActionApi = {
  powerOn: (id: number) => Promise<{ message: string }>;
  powerOff: (id: number) => Promise<{ message: string }>;
  reset: (id: number) => Promise<{ message: string }>;
  changeIp?: (id: number, ip: string) => Promise<{ message: string }>;
  changePassword?: (id: number, user: string, pwd: string) => Promise<{ message: string }>;
  destroy: (id: number) => Promise<{ message: string }>;
};

type Props = {
  instance: VpsInstanceDetail;
  actions: ActionApi;
  allowChangeIp?: boolean;
  allowChangePassword?: boolean;
  hideCredentials?: boolean;
  onUpdated?: () => void;
  backHref?: string;
  onOpenBilling?: () => void;
};

export function VpsActions({
  instance,
  actions,
  allowChangeIp = false,
  allowChangePassword = false,
  hideCredentials = false,
  onUpdated,
  backHref,
  onOpenBilling,
}: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [newIp, setNewIp] = useState(instance.ip_address || "");
  const [newPassword, setNewPassword] = useState("");
  const [passwordUser, setPasswordUser] = useState(
    instance.windows_credentials?.username ||
      (instance.os_template === "sv2019" ? "Administrador" : "Administrator")
  );

  const powerState = instance.power_state;
  const isDeleted = instance.status === "deleted";
  const isProvisioning = instance.is_provisioning;
  const canManage =
    !isDeleted && !isProvisioning && instance.status !== "creating" && instance.status !== "configuring";

  const isPoweredOn = powerState === "poweredOn";
  const isPoweredOff = powerState === "poweredOff" || powerState === "suspended";
  const billingBlocked = instance.billing?.billing_state === "suspended";
  const billingExpired =
    instance.billing?.billing_state === "grace" ||
    instance.billing?.billing_state === "suspended";
  const isAdminView = allowChangeIp || allowChangePassword;
  const canPowerOn = canManage && isPoweredOff && !billingBlocked;
  const canPowerOff = canManage && isPoweredOn;
  const canReset = canManage && isPoweredOn && !billingBlocked;
  const canGuestOps = canManage && isPoweredOn && instance.tools_ok;
  const canDestroy = canManage && (isAdminView || billingExpired);

  const run = async (label: string, fn: () => Promise<{ message: string }>) => {
    setBusy(label);
    setError("");
    setMessage("");
    try {
      const res = await fn();
      setMessage(res.message);
      onUpdated?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro na operação");
    } finally {
      setBusy(null);
    }
  };

  const destroy = async () => {
    if (!confirm(`Remover permanentemente a VPS ${instance.vm_name}? Esta ação não pode ser desfeita.`)) {
      return;
    }
    await run("destroy", () => actions.destroy(instance.id));
    if (backHref) router.push(backHref);
  };

  const btn = (
    label: string,
    action: string,
    onClick: () => void,
    enabled: boolean,
    variant: "default" | "danger" = "default"
  ) => (
    <button
      type="button"
      disabled={!!busy || !enabled}
      onClick={onClick}
      className={
        variant === "danger"
          ? "btn-ghost !text-[var(--danger)] !border-[var(--danger)]/30 hover:!bg-[var(--danger)]/10 disabled:opacity-40"
          : "btn-ghost disabled:opacity-40"
      }
    >
      {busy === action ? <BusyLabel>Aguarde…</BusyLabel> : label}
    </button>
  );

  return (
    <div className="space-y-5">
      {isProvisioning && (
        <section className="glass-card p-6 border-[var(--warning)]/25">
          <h2 className="font-semibold text-lg mb-3">Criação em andamento</h2>
          <ProvisionProgress
            progress={instance.provision_progress ?? 0}
            label={instance.provision_label}
          />
          <p className="text-xs text-muted mt-3">
            Ligar, desligar e outras configurações ficam disponíveis quando o servidor estiver pronto.
          </p>
        </section>
      )}

      {message && (
        <p className="text-sm rounded-xl px-4 py-3 border text-[var(--success)] bg-[var(--success)]/10 border-[var(--success)]/25">
          {message}
        </p>
      )}
      {error && (
        <p className="text-sm rounded-xl px-4 py-3 border text-[var(--danger)] bg-[var(--danger)]/10 border-[var(--danger)]/25">
          {error}
        </p>
      )}

      {billingBlocked && (
        <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 border border-[var(--danger)]/20 rounded-xl px-4 py-3">
          Mensalidade vencida há mais de 3 dias.{" "}
          {onOpenBilling ? (
            <button type="button" onClick={onOpenBilling} className="text-[var(--accent)] hover:underline">
              Renove na aba Plano & pagamento
            </button>
          ) : (
            "Renove para ligar o servidor novamente."
          )}
        </p>
      )}

      <section className="glass-card p-6">
        <div className="flex flex-wrap gap-3 justify-between items-center mb-5">
          <h2 className="font-semibold text-lg inline-flex items-center gap-1.5">
            Controle de energia
            <InfoTip align="end">
              Ligar inicia o Windows. Desligar desliga o servidor, como o botão de
              energia. Reiniciar força um reboot. Com o servidor desligado o RDP não
              funciona.
            </InfoTip>
          </h2>
          <PowerStateBadge powerState={powerState} />
        </div>
        <div className="flex flex-wrap gap-3">
          {btn("Ligar", "power-on", () => run("power-on", () => actions.powerOn(instance.id)), canPowerOn)}
          {btn("Desligar", "power-off", () => run("power-off", () => actions.powerOff(instance.id)), canPowerOff)}
          {btn("Reiniciar", "reset", () => run("reset", () => actions.reset(instance.id)), canReset)}
        </div>
        <p className="text-muted text-xs mt-4">
          {isPoweredOn && "Servidor online — desligar ou reiniciar quando necessário."}
          {isPoweredOff && "Servidor offline — ligue para acessar."}
          {powerState === "unknown" && "Estado indisponível. Atualize em instantes."}
          {powerState === "not_found" && "Servidor não localizado."}
        </p>
      </section>

      {!hideCredentials && (isProvisioning ? (
        <section className="glass-card p-6">
          <h2 className="font-semibold text-lg mb-2 inline-flex items-center gap-1.5">
            Conexão
            <InfoTip align="end">
              Endereço, usuário e senha para entrar no Windows aparecem aqui quando o
              servidor terminar de ser criado.
            </InfoTip>
          </h2>
          <p className="text-sm text-muted">
            Endereço RDP, usuário e senha aparecem aqui quando o servidor terminar de ser criado.
          </p>
        </section>
      ) : instance.windows_credentials ? (
        <VpsCredentialsPanel
          compact
          instanceId={instance.id}
          rdpConnectionAddress={instance.rdp_connection_address}
          osLabel={instance.os_label}
          vmName={instance.vm_name}
          username={instance.windows_credentials.username}
          password={instance.windows_credentials.password}
          hasPassword={instance.windows_credentials.has_password}
          admin={isAdminView}
        />
      ) : null)}

      {allowChangeIp && actions.changeIp && (
        <section className="glass-card p-6">
          <h2 className="font-semibold text-lg mb-4">Trocar IP local</h2>
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="text-xs text-muted block mb-1.5">Novo IP</label>
              <input
                type="text"
                value={newIp}
                onChange={(e) => setNewIp(e.target.value)}
                disabled={!!busy || !canGuestOps}
                className="input-glass font-mono"
                placeholder="192.168.0.210"
              />
            </div>
            <button
              type="button"
              disabled={!!busy || !canGuestOps || !newIp}
              onClick={() => run("change-ip", () => actions.changeIp!(instance.id, newIp))}
              className="btn-primary disabled:opacity-40"
            >
              {busy === "change-ip" ? <BusyLabel>Aplicando…</BusyLabel> : "Aplicar IP"}
            </button>
          </div>
        </section>
      )}

      {allowChangePassword && actions.changePassword && (
        <section className="glass-card p-6">
          <h2 className="font-semibold text-lg mb-4">Senha do Windows</h2>
          <div className="grid sm:grid-cols-2 gap-3 mb-4">
            <div>
              <label className="text-xs text-muted block mb-1.5">Usuário</label>
              <input
                type="text"
                value={passwordUser}
                onChange={(e) => setPasswordUser(e.target.value)}
                disabled={!!busy || !canGuestOps}
                className="input-glass"
              />
            </div>
            <div>
              <label className="text-xs text-muted block mb-1.5">Nova senha</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                disabled={!!busy || !canGuestOps}
                className="input-glass"
                placeholder="Mín. 8 caracteres"
              />
            </div>
          </div>
          <button
            type="button"
            disabled={!!busy || !canGuestOps || newPassword.length < 8}
            onClick={() =>
              run("change-password", () =>
                actions.changePassword!(instance.id, passwordUser, newPassword)
              )
            }
            className="btn-primary disabled:opacity-40"
          >
            {busy === "change-password" ? <BusyLabel>Alterando…</BusyLabel> : "Alterar senha"}
          </button>
        </section>
      )}

      <section className="glass-card p-6 border-[var(--danger)]/20">
        <h2 className="font-semibold text-[var(--danger)] mb-2">Zona de perigo</h2>
        <p className="text-muted text-sm mb-4">
          {canDestroy || isAdminView
            ? "Remove o servidor permanentemente e libera o IP."
            : "Disponível somente após o vencimento da mensalidade. Enquanto o plano estiver em dia, use a aba Plano & pagamento para renovar."}
        </p>
        {btn("Remover VPS", "destroy", destroy, canDestroy, "danger")}
      </section>
    </div>
  );
}
