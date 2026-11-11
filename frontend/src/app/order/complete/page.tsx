"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { PixPayButton, PixPaymentModal } from "@/components/PixPaymentModal";
import { PageShell } from "@/components/ui/PageShell";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SvgClock, SvgWarning } from "@/components/ui/svgs";
import { api, getToken } from "@/lib/api";
import { provisionStepLabel } from "@/lib/provisionLabels";
import { PageLoader } from "@/components/PageLoader";

type Order = {
  id: number;
  status: string;
  hostname?: string;
  order_type?: string;
  target_instance_id?: number | null;
  provision_progress?: number;
  provision_step?: string | null;
  provision_label?: string | null;
  error_message?: string | null;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  total_cents?: number;
};

const PROVISIONING_STATUSES = new Set(["paid", "provisioning"]);

function OrderCompleteContent() {
  const router = useRouter();
  const params = useSearchParams();
  const orderId = Number(params.get("order"));
  const isUpgradeFlow = params.get("upgrade") === "1";
  const isRenewFlow = params.get("renew") === "1";
  const instanceId = Number(params.get("instance"));
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");
  const [pixOpen, setPixOpen] = useState(false);
  const [pixRefreshing, setPixRefreshing] = useState(false);
  const pixAutoOpened = useRef(false);

  const isUpgrade = order?.order_type === "upgrade" || isUpgradeFlow;
  const isRenew = order?.order_type === "renewal" || isRenewFlow;
  const isProvisioning = order ? PROVISIONING_STATUSES.has(order.status) : false;
  const isPendingPayment = order?.status === "pending_payment";
  const isFailed = order?.status === "failed";
  const progress = order?.provision_progress ?? (isPendingPayment ? 0 : 5);
  const stepLabel =
    order?.provision_label ||
    provisionStepLabel(order?.provision_step) ||
    (isPendingPayment ? "Aguardando pagamento" : "Preparando...");
  const hasPix = Boolean(order?.pix_br_code);

  const title = useMemo(() => {
    if (isFailed) {
      if (isRenew) return "Falha na renovação";
      if (isUpgrade) return "Falha no upgrade";
      return "Falha ao criar servidor";
    }
    if (isProvisioning) {
      if (isRenew) return "Aplicando renovação";
      if (isUpgrade) return "Aplicando upgrade";
      return "Criando sua VPS";
    }
    if (order?.status === "active") {
      if (isRenew) return "Renovação concluída";
      if (isUpgrade) return "Upgrade concluído";
      return "Servidor pronto";
    }
    return "Pague com Pix";
  }, [isFailed, isProvisioning, isUpgrade, isRenew, order?.status]);

  const description = useMemo(() => {
    if (isFailed) {
      if (isRenew) return "Não foi possível aplicar a renovação. Tente novamente ou fale com o suporte.";
      if (isUpgrade) return "Não foi possível aplicar o upgrade. Tente novamente ou fale com o suporte.";
      return "Não foi possível concluir o provisionamento. Tente novamente ou fale com o suporte.";
    }
    if (isProvisioning) {
      return (
        stepLabel ||
        (isRenew
          ? "O novo vencimento será aplicado em instantes."
          : isUpgrade
            ? "Os novos recursos serão aplicados em instantes."
            : "Isso pode levar alguns minutos. Não feche esta página.")
      );
    }
    if (isPendingPayment) {
      return "Escaneie o QR Code ou copie o código Pix. Depois de pagar, a confirmação é automática.";
    }
    return "Seu pedido está sendo processado...";
  }, [isFailed, isProvisioning, isPendingPayment, isUpgrade, isRenew, stepLabel]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    if (!Number.isFinite(orderId)) {
      router.push("/order");
      return;
    }

    const poll = async () => {
      try {
        const data = (await api.syncOrderPayment(orderId)) as Order;
        setOrder(data);
        setError("");

        if (data.status === "pending_payment" && data.pix_br_code && !pixAutoOpened.current) {
          pixAutoOpened.current = true;
          setPixOpen(true);
        }

        if (data.status === "active") {
          const targetId = data.target_instance_id ?? (Number.isFinite(instanceId) ? instanceId : null);
          if ((data.order_type === "upgrade" || data.order_type === "renewal") && targetId) {
            const tab = data.order_type === "renewal" ? "billing" : "upgrade";
            router.replace(`/dashboard/vps/${targetId}?tab=${tab}`);
          } else {
            router.replace("/dashboard");
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Pedido não encontrado");
      }
    };

    poll();
    const interval = setInterval(poll, isProvisioning ? 2000 : 4000);
    return () => clearInterval(interval);
  }, [orderId, router, isProvisioning, instanceId]);

  useEffect(() => {
    if (!isPendingPayment) setPixOpen(false);
  }, [isPendingPayment]);

  const refreshPix = async () => {
    setPixRefreshing(true);
    try {
      const data = (await api.retryOrderCheckout(orderId)) as Order;
      setOrder(data);
      setPixOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível gerar um novo Pix");
    } finally {
      setPixRefreshing(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto text-center">
      <div className="glass-card p-10">
        <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-brand-400/30 to-indigo-500/30 flex items-center justify-center">
          {isFailed ? (
            <SvgWarning className="w-8 h-8 text-[var(--danger)]" />
          ) : (
            <SvgClock className="w-8 h-8 text-[var(--accent)] animate-pulse" />
          )}
        </div>

        <h1 className="text-2xl font-bold mb-2">{title}</h1>
        <p className="text-secondary text-sm mb-6">{description}</p>

        {(isProvisioning || isPendingPayment || order?.status === "paid") && !isFailed && (
          <div className="mb-6 text-left">
            <ProgressBar value={progress} label={stepLabel} />
          </div>
        )}

        {isPendingPayment && hasPix && !pixOpen && (
          <div className="mb-6">
            <PixPayButton onClick={() => setPixOpen(true)} />
          </div>
        )}

        {order && (
          <p className="text-xs text-muted mb-4">
            Pedido #{order.id}
            {order.hostname ? ` · ${order.hostname}` : ""}
          </p>
        )}

        {error && <p className="text-[var(--danger)] text-sm mb-4">{error}</p>}
        {isFailed && order?.error_message && (
          <p className="text-[var(--danger)] text-xs mb-4 font-mono break-all">{order.error_message}</p>
        )}

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link href="/dashboard" className={isPendingPayment ? "btn-ghost" : "btn-primary"}>
            Ir ao painel
          </Link>
          <Link href="/order" className="btn-ghost">
            Novo pedido
          </Link>
        </div>
      </div>

      <PixPaymentModal
        open={pixOpen && isPendingPayment}
        onClose={() => setPixOpen(false)}
        brCode={order?.pix_br_code ?? null}
        qrBase64={order?.pix_qr_base64 ?? null}
        amountCents={order?.total_cents}
        expiresAt={order?.pix_expires_at}
        onRefresh={refreshPix}
        refreshing={pixRefreshing}
      />
    </div>
  );
}

function OrderCompleteFallback() {
  return (
    <div className="max-w-lg mx-auto text-center">
      <PageLoader label="Carregando pedido…" compact />
    </div>
  );
}

export default function OrderCompletePage() {
  return (
    <PageShell>
      <Suspense fallback={<OrderCompleteFallback />}>
        <OrderCompleteContent />
      </Suspense>
    </PageShell>
  );
}
