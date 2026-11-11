"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { PixPaymentModal } from "@/components/PixPaymentModal";
import { AdminUserCloudFiles } from "@/components/AdminUserCloudFiles";
import { AdminDeleteAccountModal } from "@/components/AdminDeleteAccountModal";
import { AdminCreateClientModal } from "@/components/AdminCreateClientModal";
import { AdminCreateVpsModal } from "@/components/AdminCreateVpsModal";
import {
  api,
  formatPrice,
  type AdminOrderSummary,
  type AdminUserDetail,
  type AdminVpsSummary,
  type AdminWebSiteSummary,
  type User,
  type VpsInstanceAdmin,
} from "@/lib/api";
import { formatPhoneDisplay } from "@/lib/phone";
import { matchesAdminQuery } from "@/lib/adminSearch";
import { AdminSearchInput } from "@/components/AdminSearchInput";
import { BusyLabel, InlineLoader } from "@/components/PageLoader";
import { SvgChevronDown } from "@/components/ui/svgs";

type AccountSection = "cloud" | "billing" | "files" | "orders" | "sites" | "vps";

const CLOSED_SECTIONS: Record<AccountSection, boolean> = {
  cloud: false,
  billing: false,
  files: false,
  orders: false,
  sites: false,
  vps: false,
};

function ExpandableSection({
  title,
  summary,
  open,
  onToggle,
  children,
}: {
  title: string;
  summary?: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--glass-border)] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-[var(--bg-elevated)]/60 transition"
      >
        <div className="min-w-0">
          <p className="text-sm font-medium">{title}</p>
          {summary ? <p className="text-xs text-muted truncate mt-0.5">{summary}</p> : null}
        </div>
        <SvgChevronDown
          className={`w-4 h-4 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open ? (
        <div className="px-4 pb-4 space-y-3 border-t border-[var(--glass-border)] pt-3">{children}</div>
      ) : null}
    </div>
  );
}

const orderStatusInfo: Record<string, { label: string; className: string }> = {
  pending_payment: {
    label: "Aguardando pagamento",
    className: "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/25",
  },
  paid: {
    label: "Pagamento confirmado",
    className: "text-emerald-400 bg-emerald-500/10 border-emerald-500/25",
  },
  provisioning: {
    label: "Em preparação",
    className: "text-sky-400 bg-sky-500/10 border-sky-500/25",
  },
  active: {
    label: "Concluído",
    className: "text-emerald-400 bg-emerald-500/10 border-emerald-500/25",
  },
  failed: {
    label: "Falhou",
    className: "text-red-400 bg-red-500/10 border-red-500/25",
  },
  cancelled: {
    label: "Cancelado",
    className: "text-muted bg-[var(--bg-elevated)] border-[var(--glass-border)]",
  },
};

function orderKindLabel(kind: string) {
  if (kind === "vps") return "VPS";
  if (kind === "cloud") return "CyberCloud";
  if (kind === "game") return "Game";
  if (kind === "web") return "Site";
  return kind;
}

const webSiteStatusInfo: Record<string, { label: string; className: string }> = {
  running: {
    label: "Online",
    className: "text-emerald-400 bg-emerald-500/10 border-emerald-500/25",
  },
  stopped: {
    label: "Parado",
    className: "text-muted bg-[var(--bg-elevated)] border-[var(--glass-border)]",
  },
  creating: {
    label: "Criando",
    className: "text-sky-400 bg-sky-500/10 border-sky-500/25",
  },
  starting: {
    label: "Iniciando",
    className: "text-sky-400 bg-sky-500/10 border-sky-500/25",
  },
  stopping: {
    label: "Parando",
    className: "text-sky-400 bg-sky-500/10 border-sky-500/25",
  },
  error: {
    label: "Erro",
    className: "text-red-400 bg-red-500/10 border-red-500/25",
  },
};

function OrderRow({
  order,
  deleting,
  onDelete,
}: {
  order: AdminOrderSummary;
  deleting: boolean;
  onDelete: () => void;
}) {
  const status = orderStatusInfo[order.status] ?? {
    label: order.status.replaceAll("_", " "),
    className: "text-secondary bg-[var(--bg-elevated)] border-[var(--glass-border)]",
  };
  return (
    <div className="glass rounded-xl p-3 space-y-1">
      <div className="flex flex-wrap justify-between gap-2 items-start">
        <div className="min-w-0">
          <p className="font-medium text-sm truncate">{order.title}</p>
          <p className="text-xs text-secondary">{order.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border ${status.className}`}>
            {status.label}
          </span>
          {order.can_delete ? (
            <button
              type="button"
              disabled={deleting}
              onClick={onDelete}
              className="btn-ghost text-xs !py-1 !px-2 !text-[var(--danger)] !border-[var(--danger)]/30 hover:!bg-[var(--danger)]/10"
            >
              {deleting ? "…" : "Apagar"}
            </button>
          ) : null}
        </div>
      </div>
      <p className="text-xs text-muted">
        {orderKindLabel(order.kind)} #{order.id} ·{" "}
        {new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(
          new Date(order.created_at)
        )}
        {order.total_cents > 0 ? ` · ${formatPrice(order.total_cents)}` : ""}
      </p>
      {order.error_message && (
        <p className="text-xs text-red-400 break-words">{order.error_message}</p>
      )}
    </div>
  );
}

type ChargeMode = "no_charge" | "charge_now" | "defer_renewal";

function formatBytes(n: number) {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${n} B`;
}

function chargeLabel(mode: ChargeMode) {
  if (mode === "no_charge") return "Sem custo (cortesia)";
  if (mode === "charge_now") return "Cobrar agora (proporcional ao vencimento)";
  return "Cobrar na próxima renovação";
}

type Props = {
  users: User[];
  instances?: VpsInstanceAdmin[];
  onRefresh: () => void;
  onMessage: (msg: string) => void;
  onError: (msg: string) => void;
};

export function AdminAccountsPanel({ users, instances = [], onRefresh, onMessage, onError }: Props) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [cloudGb, setCloudGb] = useState(50);
  const [cloudCharge, setCloudCharge] = useState<ChargeMode>("no_charge");
  const [cloudNote, setCloudNote] = useState("");
  const [cloudBusy, setCloudBusy] = useState(false);
  const [pixOpen, setPixOpen] = useState(false);
  const [pendingPix, setPendingPix] = useState<{
    brCode: string | null;
    qrBase64: string | null;
    expiresAt: string | null;
    amountCents: number;
  } | null>(null);

  const [editVps, setEditVps] = useState<AdminVpsSummary | null>(null);
  const [vCpu, setVCpu] = useState(2);
  const [vRamGb, setVRamGb] = useState(4);
  const [vDiskGb, setVDiskGb] = useState(30);
  const [vpsCharge, setVpsCharge] = useState<ChargeMode>("no_charge");
  const [applyVmware, setApplyVmware] = useState(true);
  const [clearSuspension, setClearSuspension] = useState(false);
  const [vpsPaidUntil, setVpsPaidUntil] = useState("");
  const [vpsMonthlyReais, setVpsMonthlyReais] = useState("");
  const [vpsClearCustomMonthly, setVpsClearCustomMonthly] = useState(false);
  const [vpsClearPending, setVpsClearPending] = useState(false);
  const [vpsBusy, setVpsBusy] = useState(false);

  const [openSections, setOpenSections] = useState(CLOSED_SECTIONS);
  const [cloudPaidUntil, setCloudPaidUntil] = useState("");
  const [cloudContractedGb, setCloudContractedGb] = useState(0);
  const [cloudMonthlyCents, setCloudMonthlyCents] = useState(0);
  const [cloudClearSuspension, setCloudClearSuspension] = useState(false);
  const [cloudClearPending, setCloudClearPending] = useState(false);
  const [cloudBillingBusy, setCloudBillingBusy] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [createClientOpen, setCreateClientOpen] = useState(false);
  const [createVpsOpen, setCreateVpsOpen] = useState(false);
  const [deletingOrder, setDeletingOrder] = useState<string | null>(null);
  const [deletingSite, setDeletingSite] = useState<number | null>(null);

  const filteredUsers = useMemo(() => {
    const vmsByUser = new Map<number, string[]>();
    for (const inst of instances) {
      const names = vmsByUser.get(inst.user_id) ?? [];
      names.push(inst.vm_name);
      vmsByUser.set(inst.user_id, names);
    }
    return users.filter((user) =>
      matchesAdminQuery(query, [
        user.name,
        user.email,
        user.phone,
        formatPhoneDisplay(user.phone),
        ...(vmsByUser.get(user.id) ?? []),
      ])
    );
  }, [users, instances, query]);

  const loadDetail = useCallback(
    async (userId: number) => {
      setLoadingDetail(true);
      setSelectedId(userId);
      try {
        const d = await api.adminUserDetail(userId);
        setDetail(d);
      } catch (e) {
        onError(e instanceof Error ? e.message : "Erro ao carregar conta");
        setDetail(null);
      } finally {
        setLoadingDetail(false);
      }
    },
    [onError]
  );

  const toggleSection = (id: AccountSection) => {
    setOpenSections((current) => ({ ...current, [id]: !current[id] }));
  };

  const selectUser = (userId: number) => {
    setOpenSections(CLOSED_SECTIONS);
    setEditVps(null);
    setDeleteOpen(false);
    void loadDetail(userId);
  };

  const openVpsEdit = (vps: AdminVpsSummary) => {
    setEditVps(vps);
    setVCpu(vps.vcpu);
    setVRamGb(vps.ram_mb / 1024);
    setVDiskGb(vps.disk_gb);
    setVpsCharge("no_charge");
    setApplyVmware(true);
    setClearSuspension(false);
    setVpsPaidUntil(vps.paid_until ? new Date(vps.paid_until).toISOString().slice(0, 10) : "");
    setVpsMonthlyReais(
      vps.custom_monthly_cents != null
        ? (vps.custom_monthly_cents / 100).toFixed(2)
        : ""
    );
    setVpsClearCustomMonthly(false);
    setVpsClearPending(false);
  };

  const fillCloudBilling = () => {
    if (!detail) return;
    setCloudPaidUntil(
      detail.cloud.cloud_paid_until
        ? new Date(detail.cloud.cloud_paid_until).toISOString().slice(0, 10)
        : ""
    );
    setCloudContractedGb(detail.cloud.contracted_gb);
    setCloudMonthlyCents(detail.cloud.cloud_monthly_cents);
    setCloudClearSuspension(false);
    setCloudClearPending(false);
  };

  const toPaidUntilIso = (dateStr: string) => {
    if (!dateStr) return undefined;
    return new Date(`${dateStr}T23:59:59`).toISOString();
  };

  const submitCloudBilling = async () => {
    if (!selectedId) return;
    setCloudBillingBusy(true);
    onError("");
    try {
      const result = await api.adminUpdateCloudBilling(selectedId, {
        paid_until: cloudPaidUntil ? toPaidUntilIso(cloudPaidUntil) : undefined,
        cloud_contracted_gb: cloudContractedGb,
        cloud_monthly_cents: cloudMonthlyCents,
        clear_suspension: cloudClearSuspension,
        clear_pending_charge: cloudClearPending,
      });
      setDetail((d) => (d ? { ...d, cloud: result.cloud } : d));
      onMessage("Vencimento CyberCloud atualizado");
      onRefresh();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Erro ao atualizar billing CyberCloud");
    } finally {
      setCloudBillingBusy(false);
    }
  };

  const submitVps = async () => {
    if (!editVps) return;
    setVpsBusy(true);
    onError("");
    try {
      const resourcesChanged =
        vCpu !== editVps.vcpu ||
        vRamGb * 1024 !== editVps.ram_mb ||
        vDiskGb !== editVps.disk_gb;

      if (resourcesChanged) {
        const result = await api.adminUpdateVpsResources(editVps.id, {
          target_vcpu: vCpu,
          target_ram_mb: vRamGb * 1024,
          target_disk_gb: vDiskGb,
          charge_mode: vpsCharge,
          apply_vmware: applyVmware,
          clear_suspension: clearSuspension,
        });
        if (result.pix_br_code) {
          setPendingPix({
            brCode: result.pix_br_code,
            qrBase64: result.pix_qr_base64 ?? null,
            expiresAt: result.pix_expires_at ?? null,
            amountCents: result.charged_cents,
          });
          setPixOpen(true);
        } else if (result.checkout_url) {
          window.open(result.checkout_url, "_blank");
        }
      }

      const originalPaidUntil = editVps.paid_until
        ? new Date(editVps.paid_until).toISOString().slice(0, 10)
        : "";
      const originalMonthly =
        editVps.custom_monthly_cents != null
          ? (editVps.custom_monthly_cents / 100).toFixed(2)
          : "";

      const billingPayload: {
        paid_until?: string;
        clear_suspension?: boolean;
        clear_pending_charge?: boolean;
        custom_monthly_cents?: number;
        clear_custom_monthly_cents?: boolean;
      } = {};

      if (vpsPaidUntil && vpsPaidUntil !== originalPaidUntil) {
        billingPayload.paid_until = toPaidUntilIso(vpsPaidUntil);
      }
      if (clearSuspension) {
        billingPayload.clear_suspension = true;
      }
      if (vpsClearPending) {
        billingPayload.clear_pending_charge = true;
      }
      if (vpsClearCustomMonthly && editVps.custom_monthly_cents != null) {
        billingPayload.clear_custom_monthly_cents = true;
      } else if (vpsMonthlyReais.trim() && vpsMonthlyReais.trim() !== originalMonthly) {
        const value = parseFloat(vpsMonthlyReais.replace(",", "."));
        if (isNaN(value) || value < 0) {
          throw new Error("Valor mensal inválido.");
        }
        billingPayload.custom_monthly_cents = Math.round(value * 100);
      } else if (
        !vpsMonthlyReais.trim() &&
        editVps.custom_monthly_cents != null &&
        !vpsClearCustomMonthly
      ) {
        billingPayload.clear_custom_monthly_cents = true;
      }

      const billingChanged =
        billingPayload.paid_until !== undefined ||
        billingPayload.clear_suspension ||
        billingPayload.clear_pending_charge ||
        billingPayload.custom_monthly_cents !== undefined ||
        billingPayload.clear_custom_monthly_cents;

      if (billingChanged) {
        await api.adminUpdateVpsBilling(editVps.id, billingPayload);
      }

      if (!resourcesChanged && !billingChanged) {
        onError("Nenhuma alteração para salvar.");
        return;
      }

      onMessage(`VPS ${editVps.vm_name} atualizada`);
      setEditVps(null);
      if (selectedId) await loadDetail(selectedId);
      onRefresh();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Erro ao atualizar VPS");
    } finally {
      setVpsBusy(false);
    }
  };

  const submitCloud = async () => {
    if (!selectedId) return;
    setCloudBusy(true);
    onError("");
    try {
      const result = await api.adminAdjustCloudQuota(selectedId, {
        extra_gb: cloudGb,
        charge_mode: cloudCharge,
        note: cloudNote || undefined,
      });
      if (result.pix_br_code) {
        setPendingPix({
          brCode: result.pix_br_code,
          qrBase64: result.pix_qr_base64 ?? null,
          expiresAt: result.pix_expires_at ?? null,
          amountCents: result.charged_cents,
        });
        setPixOpen(true);
      } else if (result.checkout_url) {
        window.open(result.checkout_url, "_blank");
      }
      onMessage(
        `CyberCloud: +${result.extra_gb_added} GB` +
          (result.deferred_cents
            ? ` · R$ ${(result.deferred_cents / 100).toFixed(2)} na próxima renovação`
            : result.charged_cents
              ? ` · checkout R$ ${(result.charged_cents / 100).toFixed(2)}`
              : " · sem custo")
      );
      await loadDetail(selectedId);
      onRefresh();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Erro ao ajustar CyberCloud");
    } finally {
      setCloudBusy(false);
    }
  };

  const deleteOrder = async (order: AdminOrderSummary) => {
    if (!order.can_delete || !selectedId) return;
    if (
      !window.confirm(
        "Apagar este pedido do histórico e das métricas? A VPS continua no ar; só some o valor deste pedido."
      )
    ) {
      return;
    }
    const key = `${order.kind}-${order.id}`;
    setDeletingOrder(key);
    onError("");
    try {
      await api.adminDeleteOrder(order.kind, order.id);
      onMessage("Pedido apagado");
      await loadDetail(selectedId);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Não foi possível apagar o pedido");
    } finally {
      setDeletingOrder(null);
    }
  };

  const deleteSite = async (site: AdminWebSiteSummary) => {
    if (!selectedId) return;
    const label = site.domain || site.site_slug;
    if (
      !window.confirm(
        `Apagar o site "${label}"? O processo será parado, os arquivos removidos e o nginx atualizado.`
      )
    ) {
      return;
    }
    setDeletingSite(site.id);
    onError("");
    try {
      const result = await api.adminDeleteWebSite(site.id);
      onMessage(result.message || "Site apagado");
      await loadDetail(selectedId);
      onRefresh();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Não foi possível apagar o site");
    } finally {
      setDeletingSite(null);
    }
  };

  const toggleUser = async (user: User, field: "is_active" | "is_admin") => {
    onError("");
    try {
      await api.adminUpdateUser(user.id, { [field]: !user[field] });
      onMessage(
        field === "is_admin"
          ? user.is_admin
            ? "Acesso admin removido"
            : "Conta promovida a admin"
          : user.is_active
            ? "Conta desativada"
            : "Conta ativada"
      );
      onRefresh();
      if (selectedId === user.id) await loadDetail(user.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Erro ao atualizar conta");
    }
  };

  const resetMfa = async (user: User) => {
    onError("");
    try {
      await api.adminUpdateUser(user.id, { reset_mfa: true });
      onMessage("MFA redefinido. O admin cadastra de novo no próximo login.");
      onRefresh();
      if (selectedId === user.id) await loadDetail(user.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Erro ao redefinir MFA");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-primary !py-2" onClick={() => setCreateClientOpen(true)}>
          Cadastrar novo cliente
        </button>
        <button type="button" className="btn-ghost !py-2" onClick={() => setCreateVpsOpen(true)}>
          Criar VM
        </button>
      </div>
    <div className="grid lg:grid-cols-2 gap-8">
      <section className="glass-card p-6">
        <h2 className="font-semibold mb-3">
          Contas ({query.trim() ? `${filteredUsers.length} de ${users.length}` : users.length})
        </h2>
        <div className="mb-4">
          <AdminSearchInput value={query} onChange={setQuery} />
        </div>
        <div className="space-y-2 max-h-[560px] overflow-y-auto">
          {filteredUsers.length === 0 ? (
            <p className="text-sm text-muted">Nenhuma conta encontrada.</p>
          ) : (
            filteredUsers.map((user) => (
              <button
                key={user.id}
                type="button"
                onClick={() => selectUser(user.id)}
                className={`w-full text-left glass rounded-xl p-4 transition ${
                  selectedId === user.id ? "ring-2 ring-[var(--accent)]" : "hover:border-[var(--accent)]/40"
                }`}
              >
                <p className="font-medium">{user.name}</p>
                <p className="text-secondary text-sm">{formatPhoneDisplay(user.phone)}</p>
                {user.email ? <p className="text-xs text-muted truncate">{user.email}</p> : null}
                <p className="text-xs mt-1 text-muted">
                  {user.is_admin ? "Admin" : "Cliente"}
                  {!user.is_active && " · Inativo"}
                </p>
              </button>
            ))
          )}
        </div>
      </section>

      <section className="glass-card p-6 min-h-[320px] max-h-[820px] overflow-y-auto">
        {!selectedId ? (
          <p className="text-secondary text-sm">
            Selecione uma conta para gerenciar CyberCloud, VPS e ver o histórico de pedidos.
          </p>
        ) : loadingDetail || !detail ? (
          <InlineLoader label="Carregando conta…" />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold text-lg">{detail.name}</h2>
                <p className="text-sm text-secondary">{formatPhoneDisplay(detail.phone)}</p>
                {detail.email ? <p className="text-xs text-muted">{detail.email}</p> : (
                  <p className="text-xs text-[var(--warning)]">Sem e-mail cadastrado</p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => toggleUser(detail, "is_admin")}
                  className="btn-ghost text-xs !py-1.5 !px-3"
                >
                  {detail.is_admin ? "Remover admin" : "Tornar admin"}
                </button>
                {detail.is_admin && detail.mfa_enabled && (
                  <button
                    type="button"
                    onClick={() => resetMfa(detail)}
                    className="btn-ghost text-xs !py-1.5 !px-3"
                  >
                    Resetar MFA
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => toggleUser(detail, "is_active")}
                  className="btn-ghost text-xs !py-1.5 !px-3"
                >
                  {detail.is_active ? "Desativar" : "Ativar"}
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteOpen(true)}
                  className="btn-ghost text-xs !py-1.5 !px-3 !text-[var(--danger)] !border-[var(--danger)]/30 hover:!bg-[var(--danger)]/10"
                >
                  Excluir conta
                </button>
              </div>
            </div>

            <ExpandableSection
              title="CyberCloud"
              summary={`${formatBytes(detail.cloud.used_bytes)} de ${formatBytes(detail.cloud.quota_bytes)}${
                detail.cloud.cloud_paid_until
                  ? ` · vence ${new Date(detail.cloud.cloud_paid_until).toLocaleDateString("pt-BR")}`
                  : ""
              }`}
              open={openSections.cloud}
              onToggle={() => toggleSection("cloud")}
            >
              <p className="text-sm text-secondary">
                Contratado{" "}
                {detail.cloud.contracted_gb > 0
                  ? `${detail.cloud.contracted_gb} GB`
                  : formatBytes(detail.cloud.extra_bytes)}
                {detail.cloud.cloud_monthly_cents > 0 &&
                  ` · ${formatPrice(detail.cloud.cloud_monthly_cents)}/mês`}
                {detail.cloud.billing?.billing_state === "grace" && " · em carência"}
                {detail.cloud.cloud_suspended_for_billing && " · suspenso"}
              </p>
              {detail.cloud.admin_pending_cloud_charge_cents > 0 && (
                <p className="text-xs text-amber-400">
                  Pendente na renovação: {formatPrice(detail.cloud.admin_pending_cloud_charge_cents)}
                </p>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                <input
                  type="number"
                  min={1}
                  value={cloudGb}
                  onChange={(e) => setCloudGb(Number(e.target.value))}
                  className="input-glass w-24"
                  placeholder="GB"
                />
                <select
                  value={cloudCharge}
                  onChange={(e) => setCloudCharge(e.target.value as ChargeMode)}
                  className="input-glass flex-1 min-w-[180px]"
                >
                  <option value="no_charge">{chargeLabel("no_charge")}</option>
                  <option value="charge_now">{chargeLabel("charge_now")}</option>
                  <option value="defer_renewal">{chargeLabel("defer_renewal")}</option>
                </select>
              </div>
              <input
                type="text"
                placeholder="Observação (opcional)"
                value={cloudNote}
                onChange={(e) => setCloudNote(e.target.value)}
                className="input-glass w-full text-sm"
              />
              <button
                type="button"
                disabled={cloudBusy}
                onClick={submitCloud}
                className="btn-primary text-sm !py-2"
              >
                {cloudBusy ? <BusyLabel>Aplicando…</BusyLabel> : `Adicionar ${cloudGb} GB`}
              </button>
            </ExpandableSection>

            <ExpandableSection
              title="Editar vencimento"
              summary={
                detail.cloud.cloud_paid_until
                  ? `Vence ${new Date(detail.cloud.cloud_paid_until).toLocaleDateString("pt-BR")}`
                  : "Sem vencimento definido"
              }
              open={openSections.billing}
              onToggle={() => {
                if (!openSections.billing) fillCloudBilling();
                toggleSection("billing");
              }}
            >
              <div className="grid sm:grid-cols-3 gap-2">
                <label className="text-xs">
                  Vencimento
                  <input
                    type="date"
                    value={cloudPaidUntil}
                    onChange={(e) => setCloudPaidUntil(e.target.value)}
                    className="input-glass w-full mt-1"
                  />
                </label>
                <label className="text-xs">
                  GB contratados
                  <input
                    type="number"
                    min={0}
                    value={cloudContractedGb}
                    onChange={(e) => setCloudContractedGb(Number(e.target.value))}
                    className="input-glass w-full mt-1"
                  />
                </label>
                <label className="text-xs">
                  Mensalidade (centavos)
                  <input
                    type="number"
                    min={0}
                    value={cloudMonthlyCents}
                    onChange={(e) => setCloudMonthlyCents(Number(e.target.value))}
                    className="input-glass w-full mt-1"
                  />
                </label>
              </div>
              <label className="flex items-center gap-2 text-xs text-secondary">
                <input
                  type="checkbox"
                  checked={cloudClearSuspension}
                  onChange={(e) => setCloudClearSuspension(e.target.checked)}
                />
                Remover suspensão por billing
              </label>
              <label className="flex items-center gap-2 text-xs text-secondary">
                <input
                  type="checkbox"
                  checked={cloudClearPending}
                  onChange={(e) => setCloudClearPending(e.target.checked)}
                />
                Zerar cobrança pendente na renovação
              </label>
              <button
                type="button"
                disabled={cloudBillingBusy}
                onClick={submitCloudBilling}
                className="btn-primary text-sm !py-2 w-full"
              >
                {cloudBillingBusy ? <BusyLabel>Salvando…</BusyLabel> : "Salvar CyberCloud"}
              </button>
            </ExpandableSection>

            <ExpandableSection
              title="Arquivos CyberCloud"
              summary="Somente leitura"
              open={openSections.files}
              onToggle={() => toggleSection("files")}
            >
              {openSections.files ? (
                <AdminUserCloudFiles key={detail.id} userId={detail.id} onError={onError} />
              ) : null}
            </ExpandableSection>

            <ExpandableSection
              title="Histórico de pedidos"
              summary={`${detail.orders?.length ?? 0} pedido(s)`}
              open={openSections.orders}
              onToggle={() => toggleSection("orders")}
            >
              {(detail.orders?.length ?? 0) === 0 ? (
                <p className="text-secondary text-sm">Nenhum pedido nesta conta.</p>
              ) : (
                <div className="space-y-2 max-h-[320px] overflow-y-auto">
                  {(detail.orders ?? []).map((order) => (
                    <OrderRow
                      key={`${order.kind}-${order.id}`}
                      order={order}
                      deleting={deletingOrder === `${order.kind}-${order.id}`}
                      onDelete={() => void deleteOrder(order)}
                    />
                  ))}
                </div>
              )}
            </ExpandableSection>

            <ExpandableSection
              title="Sites"
              summary={`${detail.web_sites?.length ?? 0} site(s)`}
              open={openSections.sites}
              onToggle={() => toggleSection("sites")}
            >
              {(detail.web_sites?.length ?? 0) === 0 ? (
                <p className="text-secondary text-sm">Nenhum site.</p>
              ) : (
                <div className="space-y-2">
                  {(detail.web_sites ?? []).map((site) => {
                    const status = webSiteStatusInfo[site.status] ?? {
                      label: site.status.replaceAll("_", " "),
                      className: "text-secondary bg-[var(--bg-elevated)] border-[var(--glass-border)]",
                    };
                    return (
                      <div
                        key={site.id}
                        className="flex flex-wrap gap-2 justify-between items-start glass rounded-xl p-3"
                      >
                        <div className="min-w-0">
                          <p className="font-medium text-sm truncate">
                            {site.domain || site.site_slug}
                          </p>
                          <p className="text-xs text-secondary mt-0.5">
                            /s/{site.site_slug}/ · porta {site.port} · {site.ram_mb} MB RAM ·{" "}
                            {site.disk_mb} MB disco
                            {site.php_enabled ? " · PHP" : ""}
                          </p>
                          {site.paid_until && (
                            <p className="text-xs text-muted">
                              Vence {new Date(site.paid_until).toLocaleDateString("pt-BR")}
                            </p>
                          )}
                          {site.suspended_for_billing && (
                            <p className="text-xs text-amber-400">Suspenso por billing</p>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-2 items-center">
                          <span
                            className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border ${status.className}`}
                          >
                            {status.label}
                          </span>
                          <button
                            type="button"
                            disabled={deletingSite === site.id}
                            onClick={() => void deleteSite(site)}
                            className="btn-ghost text-xs !py-1.5 !px-3 !text-[var(--danger)] !border-[var(--danger)]/30 hover:!bg-[var(--danger)]/10"
                          >
                            {deletingSite === site.id ? "…" : "Apagar site"}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </ExpandableSection>

            <ExpandableSection
              title="VPS"
              summary={`${detail.vps_instances.length} servidor(es)`}
              open={openSections.vps}
              onToggle={() => {
                if (openSections.vps) setEditVps(null);
                toggleSection("vps");
              }}
            >
              {detail.vps_instances.length === 0 ? (
                <p className="text-secondary text-sm">Nenhuma VPS.</p>
              ) : (
                <div className="space-y-2">
                  {detail.vps_instances.map((vps) => (
                    <div
                      key={vps.id}
                      className="flex flex-wrap gap-2 justify-between items-start glass rounded-xl p-3"
                    >
                      <div>
                        <Link
                          href={`/admin/vps/${vps.id}`}
                          className="font-medium text-[var(--accent)] hover:underline"
                        >
                          {vps.vm_name}
                        </Link>
                        <p className="text-xs text-secondary mt-0.5">
                          {vps.vcpu} vCPU · {vps.ram_mb / 1024} GB RAM · {vps.disk_gb} GB disco
                        </p>
                        {vps.paid_until && (
                          <p className="text-xs text-muted">
                            Vence {new Date(vps.paid_until).toLocaleDateString("pt-BR")}
                            {" · "}
                            {vps.custom_monthly_cents != null
                              ? `${formatPrice(vps.custom_monthly_cents)}/mês (personalizado)`
                              : vps.monthly_cents != null
                                ? `${formatPrice(vps.monthly_cents)}/mês`
                                : "—"}
                          </p>
                        )}
                        {vps.admin_pending_charge_cents > 0 && (
                          <p className="text-xs text-amber-400">
                            +{formatPrice(vps.admin_pending_charge_cents)} na renovação
                          </p>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => openVpsEdit(vps)}
                          className="btn-ghost text-xs !py-1.5 !px-3"
                        >
                          Editar VPS
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            {editVps && (
              <div className="rounded-xl border border-[var(--accent)]/30 bg-[var(--accent)]/5 p-4 space-y-4">
                <p className="font-medium text-sm">Editar {editVps.vm_name}</p>

                <div>
                  <p className="text-xs font-medium text-secondary mb-2 uppercase tracking-wide">Recursos</p>
                  <div className="grid grid-cols-3 gap-2">
                    <label className="text-xs">
                      vCPU
                      <input
                        type="number"
                        min={1}
                        value={vCpu}
                        onChange={(e) => setVCpu(Number(e.target.value))}
                        className="input-glass w-full mt-1"
                      />
                    </label>
                    <label className="text-xs">
                      RAM (GB)
                      <input
                        type="number"
                        min={1}
                        value={vRamGb}
                        onChange={(e) => setVRamGb(Number(e.target.value))}
                        className="input-glass w-full mt-1"
                      />
                    </label>
                    <label className="text-xs">
                      Disco (GB)
                      <input
                        type="number"
                        min={30}
                        value={vDiskGb}
                        onChange={(e) => setVDiskGb(Number(e.target.value))}
                        className="input-glass w-full mt-1"
                      />
                    </label>
                  </div>
                  <select
                    value={vpsCharge}
                    onChange={(e) => setVpsCharge(e.target.value as ChargeMode)}
                    className="input-glass w-full text-sm mt-2"
                  >
                    <option value="no_charge">{chargeLabel("no_charge")}</option>
                    <option value="charge_now">{chargeLabel("charge_now")}</option>
                    <option value="defer_renewal">{chargeLabel("defer_renewal")}</option>
                  </select>
                  <label className="flex items-center gap-2 text-xs text-secondary mt-2">
                    <input
                      type="checkbox"
                      checked={applyVmware}
                      onChange={(e) => setApplyVmware(e.target.checked)}
                    />
                    Aplicar no servidor (upgrade de hardware/disco)
                  </label>
                </div>

                <div className="border-t border-[var(--glass-border)] pt-4">
                  <p className="text-xs font-medium text-secondary mb-2 uppercase tracking-wide">
                    Vencimento e valor
                  </p>
                  <div className="grid sm:grid-cols-2 gap-2">
                    <label className="text-xs">
                      Data de vencimento
                      <input
                        type="date"
                        value={vpsPaidUntil}
                        onChange={(e) => setVpsPaidUntil(e.target.value)}
                        className="input-glass w-full mt-1"
                      />
                    </label>
                    <label className="text-xs">
                      Valor mensal (R$)
                      <div className="relative mt-1">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary text-sm">
                          R$
                        </span>
                        <input
                          type="number"
                          min={0}
                          step={0.01}
                          value={vpsMonthlyReais}
                          onChange={(e) => setVpsMonthlyReais(e.target.value)}
                          placeholder={
                            editVps.monthly_cents != null
                              ? (editVps.monthly_cents / 100).toFixed(2)
                              : "0.00"
                          }
                          className="input-glass w-full pl-9"
                        />
                      </div>
                    </label>
                  </div>
                  <p className="text-xs text-muted mt-2">
                    Plano:{" "}
                    {editVps.monthly_cents != null ? formatPrice(editVps.monthly_cents) + "/mês" : "—"}
                    {editVps.custom_monthly_cents != null &&
                      ` · Personalizado: ${formatPrice(editVps.custom_monthly_cents)}/mês`}
                  </p>
                  <label className="flex items-center gap-2 text-xs text-secondary mt-2">
                    <input
                      type="checkbox"
                      checked={vpsClearCustomMonthly}
                      onChange={(e) => setVpsClearCustomMonthly(e.target.checked)}
                    />
                    Voltar ao preço do plano (remover valor personalizado)
                  </label>
                </div>

                <div className="border-t border-[var(--glass-border)] pt-3 space-y-2">
                  <label className="flex items-center gap-2 text-xs text-secondary">
                    <input
                      type="checkbox"
                      checked={clearSuspension}
                      onChange={(e) => setClearSuspension(e.target.checked)}
                    />
                    Remover suspensão por billing
                  </label>
                  <label className="flex items-center gap-2 text-xs text-secondary">
                    <input
                      type="checkbox"
                      checked={vpsClearPending}
                      onChange={(e) => setVpsClearPending(e.target.checked)}
                    />
                    Zerar cobrança pendente na renovação
                  </label>
                </div>

                <div className="flex gap-2">
                  <button type="button" onClick={() => setEditVps(null)} className="btn-ghost text-sm flex-1">
                    Cancelar
                  </button>
                  <button
                    type="button"
                    disabled={vpsBusy}
                    onClick={submitVps}
                    className="btn-primary text-sm flex-1"
                  >
                    {vpsBusy ? <BusyLabel>Salvando…</BusyLabel> : "Salvar alterações"}
                  </button>
                </div>
              </div>
            )}
            </ExpandableSection>
          </div>
        )}
      </section>
      <PixPaymentModal
        open={pixOpen && pendingPix != null}
        onClose={() => setPixOpen(false)}
        brCode={pendingPix?.brCode ?? null}
        qrBase64={pendingPix?.qrBase64 ?? null}
        amountCents={pendingPix?.amountCents}
        expiresAt={pendingPix?.expiresAt}
      />
      <AdminDeleteAccountModal
        userId={deleteOpen ? selectedId : null}
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onDeleted={(msg) => {
          setDetail(null);
          setSelectedId(null);
          onMessage(msg);
          onRefresh();
        }}
        onError={onError}
      />
      <AdminCreateClientModal
        open={createClientOpen}
        onClose={() => setCreateClientOpen(false)}
        onCreated={(msg) => {
          onMessage(msg);
          onRefresh();
        }}
        onError={onError}
      />
      <AdminCreateVpsModal
        open={createVpsOpen}
        users={users}
        preselectedUserId={selectedId}
        onClose={() => setCreateVpsOpen(false)}
        onCreated={(msg) => {
          onMessage(msg);
          onRefresh();
          if (selectedId) void loadDetail(selectedId);
        }}
        onError={onError}
      />
    </div>
    </div>
  );
}
