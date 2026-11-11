"use client";

import { useEffect, useState } from "react";
import {
  api,
  type AdminAccountDeletionPreview,
} from "@/lib/api";
import { formatPhoneDisplay, normalizePhoneInput } from "@/lib/phone";
import { BusyLabel, InlineLoader } from "@/components/PageLoader";

type Props = {
  userId: number | null;
  open: boolean;
  onClose: () => void;
  onDeleted: (message: string) => void;
  onError: (message: string) => void;
};

function formatBytes(n: number) {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${n} B`;
}

function gameLabel(type: string) {
  if (type === "samp") return "SA-MP";
  if (type === "mta") return "MTA";
  if (type === "minecraft") return "Minecraft";
  if (type === "fivem") return "FiveM";
  return type;
}

export function AdminDeleteAccountModal({ userId, open, onClose, onDeleted, onError }: Props) {
  const [preview, setPreview] = useState<AdminAccountDeletionPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmPhone, setConfirmPhone] = useState("");

  useEffect(() => {
    if (!open || userId == null) {
      setPreview(null);
      setConfirmPhone("");
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .adminUserDeletionPreview(userId)
      .then((data) => {
        if (!cancelled) setPreview(data);
      })
      .catch((err) => {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : "Erro ao carregar o que será excluído");
          onClose();
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, userId, onClose, onError]);

  useEffect(() => {
    if (!open) return;
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

  if (!open || userId == null) return null;

  const phoneOk =
    preview != null &&
    normalizePhoneInput(confirmPhone) === normalizePhoneInput(preview.phone);

  const submit = async () => {
    if (!preview || !phoneOk || busy) return;
    setBusy(true);
    try {
      const result = await api.adminDeleteUser(preview.id, normalizePhoneInput(confirmPhone));
      const bits = [
        result.destroyed_vms.length ? `${result.destroyed_vms.length} VPS` : null,
        result.stopped_game_servers ? `${result.stopped_game_servers} game(s)` : null,
        result.deleted_web_sites ? `${result.deleted_web_sites} site(s)` : null,
        result.deleted_cloud_files ? `${result.deleted_cloud_files} item(ns) CyberCloud` : null,
      ].filter(Boolean);
      onDeleted(
        bits.length
          ? `Conta de ${preview.name} excluída (${bits.join(", ")}).`
          : `Conta de ${preview.name} excluída.`
      );
      onClose();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Não foi possível excluir a conta");
    } finally {
      setBusy(false);
    }
  };

  const orderTotal =
    (preview?.orders.vps ?? 0) +
    (preview?.orders.cloud ?? 0) +
    (preview?.orders.game ?? 0) +
    (preview?.orders.web ?? 0);

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60"
      onClick={() => {
        if (!busy) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-account-title"
        className="glass-card w-full max-w-lg max-h-[90vh] flex flex-col p-6 relative"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="delete-account-title" className="text-lg font-bold text-[var(--danger)] pr-8">
          Excluir conta
        </h2>
        {loading || !preview ? (
          <div className="py-8">
            <InlineLoader label="Listando o que será apagado…" />
          </div>
        ) : (
          <>
            <p className="text-sm text-secondary mt-1">
              {preview.name} · {formatPhoneDisplay(preview.phone)}
              {preview.is_admin ? " · Admin" : ""}
            </p>
            <p className="text-xs text-[var(--danger)] mt-3">
              Isto apaga a conta, as VMs no ESXi, servidores de jogo e arquivos do CyberCloud. Não
              dá para desfazer.
            </p>

            <div className="overflow-y-auto mt-4 space-y-3 pr-1 text-sm">
              {preview.warnings.length > 0 ? (
                <ul className="text-xs text-amber-400 space-y-1 list-disc pl-4">
                  {preview.warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : null}

              <section className="rounded-xl border border-[var(--glass-border)] p-3 space-y-1">
                <p className="font-medium">VPS ({preview.vps.length})</p>
                {preview.vps.length === 0 ? (
                  <p className="text-xs text-muted">Nenhuma VM ativa.</p>
                ) : (
                  preview.vps.map((vm) => (
                    <p key={vm.id} className="text-xs text-secondary">
                      {vm.vm_name}
                      {vm.ip_address ? ` · ${vm.ip_address}` : ""} · {vm.vcpu} vCPU ·{" "}
                      {vm.ram_mb / 1024} GB RAM · {vm.disk_gb} GB
                    </p>
                  ))
                )}
              </section>

              <section className="rounded-xl border border-[var(--glass-border)] p-3 space-y-1">
                <p className="font-medium">Servidores de jogo ({preview.game_servers.length})</p>
                {preview.game_servers.length === 0 ? (
                  <p className="text-xs text-muted">Nenhum servidor de jogo.</p>
                ) : (
                  preview.game_servers.map((server) => (
                    <p key={server.id} className="text-xs text-secondary">
                      {server.server_name} · {gameLabel(server.game_type)} · porta {server.port}
                    </p>
                  ))
                )}
              </section>

              <section className="rounded-xl border border-[var(--glass-border)] p-3 space-y-1">
                <p className="font-medium">Sites ({preview.web_sites?.length ?? 0})</p>
                {(preview.web_sites?.length ?? 0) === 0 ? (
                  <p className="text-xs text-muted">Nenhum site.</p>
                ) : (
                  (preview.web_sites ?? []).map((site) => (
                    <p key={site.id} className="text-xs text-secondary">
                      {site.domain || site.site_slug} · porta {site.port}
                    </p>
                  ))
                )}
              </section>

              <section className="rounded-xl border border-[var(--glass-border)] p-3 space-y-1">
                <p className="font-medium">CyberCloud</p>
                <p className="text-xs text-secondary">
                  {preview.cloud.files} arquivo(s) · {preview.cloud.folders} pasta(s) ·{" "}
                  {formatBytes(preview.cloud.used_bytes)}
                </p>
              </section>

              <section className="rounded-xl border border-[var(--glass-border)] p-3 space-y-1">
                <p className="font-medium">Pedidos ({orderTotal})</p>
                <p className="text-xs text-secondary">
                  {preview.orders.vps} VPS · {preview.orders.game} game · {preview.orders.cloud}{" "}
                  CyberCloud · {preview.orders.web ?? 0} site
                  {preview.orders.pending_payment
                    ? ` · ${preview.orders.pending_payment} aguardando pagamento`
                    : ""}
                </p>
              </section>
            </div>

            <label className="block text-xs text-secondary mt-4">
              Digite o telefone <span className="font-mono">{formatPhoneDisplay(preview.phone)}</span>{" "}
              para confirmar
              <input
                type="tel"
                inputMode="numeric"
                autoComplete="off"
                value={confirmPhone}
                onChange={(event) => setConfirmPhone(event.target.value)}
                disabled={busy}
                className="input-glass w-full mt-1"
                placeholder="DDD + número"
              />
            </label>

            <div className="flex gap-2 mt-4">
              <button type="button" disabled={busy} onClick={onClose} className="btn-ghost flex-1 text-sm">
                Cancelar
              </button>
              <button
                type="button"
                disabled={busy || !phoneOk}
                onClick={() => void submit()}
                className="flex-1 text-sm font-semibold rounded-xl py-2.5 bg-[var(--danger)]/90 hover:bg-[var(--danger)] text-white disabled:opacity-40"
              >
                {busy ? <BusyLabel>Excluindo…</BusyLabel> : "Excluir tudo"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
