"use client";

import { useEffect, useMemo, useState } from "react";
import { PixPaymentModal, pixIsExpired } from "@/components/PixPaymentModal";
import { SvgCloud, SvgDocument, SvgGame, SvgGlobe, SvgRefresh, SvgServer, SvgTrash } from "@/components/ui/svgs";
import {
  api,
  formatPrice,
  type CloudStorageOrder,
  type GameOrder,
  type VpsOrder,
  type WebOrder,
} from "@/lib/api";
import { GAME_HOSTING_ENABLED, WEB_HOSTING_ENABLED } from "@/lib/features";
import { BusyLabel, PageLoader } from "@/components/PageLoader";

type OrderKind = "vps" | "game" | "cloud" | "web";

type ClientOrder = {
  key: string;
  id: number;
  kind: OrderKind;
  title: string;
  description: string;
  status: string;
  totalCents: number;
  createdAt: string;
  pixBrCode: string | null;
  pixQrBase64: string | null;
  pixExpiresAt: string | null;
};

const statusInfo: Record<string, { label: string; className: string }> = {
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

const orderTypeLabel: Record<string, string> = {
  new: "Nova VPS",
  upgrade: "Upgrade de VPS",
  renewal: "Renovação de VPS",
  admin: "Ajuste da equipe",
};

const gameLabel: Record<string, string> = {
  samp: "SA-MP",
  mta: "MTA",
  minecraft: "Minecraft",
  fivem: "FiveM",
};

function mapVps(order: VpsOrder): ClientOrder {
  return {
    key: `vps-${order.id}`,
    id: order.id,
    kind: "vps",
    title: orderTypeLabel[order.order_type] ?? "Pedido VPS",
    description:
      order.notes
        ? order.notes
        : order.order_type === "new"
          ? `${order.hostname} · ${order.vcpu} vCPU · ${Math.round(order.ram_mb / 1024)} GB RAM`
          : order.hostname,
    status: order.status,
    totalCents: order.total_cents,
    createdAt: order.created_at,
    pixBrCode: order.pix_br_code ?? null,
    pixQrBase64: order.pix_qr_base64 ?? null,
    pixExpiresAt: order.pix_expires_at ?? null,
  };
}

function mapGame(order: GameOrder): ClientOrder {
  return {
    key: `game-${order.id}`,
    id: order.id,
    kind: "game",
    title: `Servidor ${gameLabel[order.game_type] ?? order.game_type}`,
    description: `${order.server_name} · ${order.slots} slots · ${Math.round(order.ram_mb / 1024)} GB RAM`,
    status: order.status,
    totalCents: order.total_cents,
    createdAt: order.created_at,
    pixBrCode: order.pix_br_code ?? null,
    pixQrBase64: order.pix_qr_base64 ?? null,
    pixExpiresAt: order.pix_expires_at ?? null,
  };
}

function mapCloud(order: CloudStorageOrder): ClientOrder {
  const renewal = Boolean(order.renewal_months);
  return {
    key: `cloud-${order.id}`,
    id: order.id,
    kind: "cloud",
    title: order.notes ? "Ajuste da equipe" : renewal ? "Renovação CyberCloud" : "Espaço CyberCloud",
    description: order.notes
      ? order.notes
      : renewal
        ? `${order.renewal_months} mês(es)`
        : `+${order.extra_gb} GB de armazenamento`,
    status: order.status,
    totalCents: order.total_cents,
    createdAt: order.created_at,
    pixBrCode: order.pix_br_code ?? null,
    pixQrBase64: order.pix_qr_base64 ?? null,
    pixExpiresAt: order.pix_expires_at ?? null,
  };
}

function mapWeb(order: WebOrder): ClientOrder {
  const renewal = order.order_type === "renewal" || Boolean(order.renewal_months);
  return {
    key: `web-${order.id}`,
    id: order.id,
    kind: "web",
    title: renewal ? "Renovação de site" : "Hospedagem de site",
    description: renewal
      ? `${order.domain || order.site_slug} · ${order.renewal_months ?? 1} mês(es)`
      : `${order.domain || `/s/${order.site_slug}`} · ${order.ram_mb} MB RAM · ${order.php_enabled ? "PHP" : "estático"}`,
    status: order.status,
    totalCents: order.total_cents,
    createdAt: order.created_at,
    pixBrCode: order.pix_br_code ?? null,
    pixQrBase64: order.pix_qr_base64 ?? null,
    pixExpiresAt: order.pix_expires_at ?? null,
  };
}

function OrderIcon({ kind }: { kind: OrderKind }) {
  const Icon =
    kind === "vps" ? SvgServer : kind === "game" ? SvgGame : kind === "web" ? SvgGlobe : SvgCloud;
  return <Icon className="w-5 h-5" />;
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<ClientOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [pixOrder, setPixOrder] = useState<ClientOrder | null>(null);

  const load = async () => {
    setError("");
    try {
      const [vps, games, cloud, web] = await Promise.all([
        api.orders(),
        GAME_HOSTING_ENABLED ? api.gameOrders() : Promise.resolve([] as GameOrder[]),
        api.cloudStorageOrders(),
        WEB_HOSTING_ENABLED ? api.webOrders() : Promise.resolve([] as WebOrder[]),
      ]);
      setOrders(
        [...vps.map(mapVps), ...games.map(mapGame), ...cloud.map(mapCloud), ...web.map(mapWeb)].sort(
          (a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt)
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar os pedidos");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const pending = useMemo(
    () => orders.filter((order) => order.status === "pending_payment"),
    [orders]
  );
  const history = useMemo(
    () => orders.filter((order) => order.status !== "pending_payment"),
    [orders]
  );

  const syncOrder = async (order: ClientOrder, openPix: boolean) => {
    setBusyKey(order.key);
    setError("");
    try {
      let updated: ClientOrder;
      if (order.kind === "vps") {
        updated = mapVps(await api.syncOrderPayment(order.id));
      } else if (order.kind === "game") {
        updated = mapGame(await api.syncGameOrderPayment(order.id));
      } else if (order.kind === "web") {
        updated = mapWeb(await api.syncWebOrderPayment(order.id));
      } else {
        const cloud = await api.cloudStorageSyncPayment(order.id);
        updated = {
          ...order,
          status: cloud.status,
          totalCents: cloud.total_cents ?? order.totalCents,
          pixBrCode: cloud.pix_br_code ?? null,
          pixQrBase64: cloud.pix_qr_base64 ?? null,
          pixExpiresAt: cloud.pix_expires_at ?? null,
        };
      }
      setOrders((current) => current.map((item) => (item.key === order.key ? updated : item)));
      if (updated.status === "pending_payment" && openPix) setPixOrder(updated);
      else setPixOrder(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível atualizar o pedido");
    } finally {
      setBusyKey(null);
    }
  };

  useEffect(() => {
    if (!pixOrder || pixOrder.status !== "pending_payment" || busyKey) return;
    const timer = window.setTimeout(() => {
      void syncOrder(pixOrder, true);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [pixOrder, busyKey]);

  const openPix = (order: ClientOrder) => {
    if (!order.pixBrCode || pixIsExpired(order.pixExpiresAt)) {
      void syncOrder(order, true);
      return;
    }
    setPixOrder(order);
  };

  const cancelOrder = async (order: ClientOrder) => {
    if (
      !window.confirm(
        `Cancelar o pedido “${order.title}”? Se você pagar o Pix depois, o pedido volta a ser processado automaticamente.`
      )
    ) {
      return;
    }
    setBusyKey(order.key);
    setError("");
    try {
      if (order.kind === "vps") await api.deleteOrder(order.id);
      else if (order.kind === "game") await api.deleteGameOrder(order.id);
      else if (order.kind === "web") await api.deleteWebOrder(order.id);
      else await api.deleteCloudStorageOrder(order.id);
      setOrders((current) =>
        current.map((item) => (item.key === order.key ? { ...item, status: "cancelled" } : item))
      );
      if (pixOrder?.key === order.key) setPixOrder(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível cancelar o pedido");
    } finally {
      setBusyKey(null);
    }
  };

  const renderOrder = (order: ClientOrder) => {
    const status = statusInfo[order.status] ?? {
      label: order.status.replaceAll("_", " "),
      className: "text-secondary bg-[var(--bg-elevated)] border-[var(--glass-border)]",
    };
    const isPending = order.status === "pending_payment";
    const busy = busyKey === order.key;

    return (
      <article key={order.key} className="glass-card p-5 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="flex gap-3 min-w-0">
            <div className="w-10 h-10 shrink-0 rounded-xl bg-[var(--accent)]/10 text-[var(--accent)] flex items-center justify-center">
              <OrderIcon kind={order.kind} />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold truncate">{order.title}</h3>
              <p className="text-sm text-secondary mt-0.5">{order.description}</p>
              <p className="text-xs text-muted mt-2">
                Pedido #{order.id} ·{" "}
                {new Intl.DateTimeFormat("pt-BR", {
                  dateStyle: "short",
                  timeStyle: "short",
                }).format(new Date(order.createdAt))}
              </p>
            </div>
          </div>
          <div className="sm:text-right shrink-0">
            <p className="text-lg font-bold">{formatPrice(order.totalCents)}</p>
            <span
              className={`inline-flex mt-1 rounded-full border px-2.5 py-1 text-xs font-medium ${status.className}`}
            >
              {status.label}
            </span>
          </div>
        </div>

        {isPending && (
          <div className="flex flex-col sm:flex-row gap-2 mt-5 pt-4 border-t border-[var(--glass-border)]">
            <button
              type="button"
              onClick={() => openPix(order)}
              disabled={busy}
              className="btn-primary flex-1 !py-2.5"
            >
              {busy ? <BusyLabel>Atualizando…</BusyLabel> : "Abrir QR Code Pix"}
            </button>
            <button
              type="button"
              onClick={() => void cancelOrder(order)}
              disabled={busy}
              className="btn-ghost !py-2.5 text-red-400 hover:text-red-300"
            >
              <SvgTrash className="w-4 h-4" />
              Cancelar
            </button>
          </div>
        )}
      </article>
    );
  };

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-5 mb-8">
        <div>
          <p className="text-sm font-medium text-[var(--accent)] mb-2 tracking-wide uppercase">
            Conta
          </p>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">Meus pedidos</h1>
          <p className="text-secondary mt-2">
            Acompanhe pagamentos e consulte o histórico das suas compras.
          </p>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading} className="btn-ghost">
          <SvgRefresh className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-red-500/25 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <PageLoader label="Carregando pedidos…" />
      ) : orders.length === 0 ? (
        <div className="glass-card py-20 px-6 text-center">
          <SvgDocument className="w-12 h-12 mx-auto text-muted mb-4" />
          <h2 className="text-xl font-semibold">Nenhum pedido ainda</h2>
          <p className="text-muted mt-2">Seus pedidos aparecerão aqui.</p>
        </div>
      ) : (
        <div className="space-y-10">
          {pending.length > 0 && (
            <section>
              <h2 className="text-xl font-semibold mb-4">Aguardando pagamento</h2>
              <div className="grid lg:grid-cols-2 gap-4">{pending.map(renderOrder)}</div>
            </section>
          )}

          <section>
            <h2 className="text-xl font-semibold mb-4">Histórico</h2>
            {history.length > 0 ? (
              <div className="grid lg:grid-cols-2 gap-4">{history.map(renderOrder)}</div>
            ) : (
              <div className="glass-card p-8 text-center text-muted">
                Nenhum pagamento concluído ainda.
              </div>
            )}
          </section>
        </div>
      )}

      <PixPaymentModal
        open={Boolean(pixOrder)}
        onClose={() => setPixOrder(null)}
        onRefresh={
          pixOrder ? () => syncOrder(pixOrder, true) : undefined
        }
        refreshing={pixOrder ? busyKey === pixOrder.key : false}
        brCode={pixOrder?.pixBrCode ?? null}
        qrBase64={pixOrder?.pixQrBase64 ?? null}
        expiresAt={pixOrder?.pixExpiresAt ?? null}
        amountCents={pixOrder?.totalCents}
        title={pixOrder ? `Pix · ${pixOrder.title}` : "Pague com Pix"}
      />
    </>
  );
}
