"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { PixPayButton, PixPaymentModal } from "@/components/PixPaymentModal";
import { PageShell } from "@/components/ui/PageShell";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SvgClock, SvgWarning } from "@/components/ui/svgs";
import { api, getToken, type WebOrder } from "@/lib/api";

const PROVISIONING = new Set(["paid", "provisioning"]);

function WebOrderCompleteContent() {
  const router = useRouter();
  const params = useSearchParams();
  const orderId = Number(params.get("order"));
  const isRenewFlow = params.get("renew") === "1";
  const siteId = Number(params.get("site"));
  const [order, setOrder] = useState<WebOrder | null>(null);
  const [error, setError] = useState("");
  const [pixOpen, setPixOpen] = useState(false);
  const [pixRefreshing, setPixRefreshing] = useState(false);
  const pixAutoOpened = useRef(false);

  const isProvisioning = order ? PROVISIONING.has(order.status) : false;
  const isPending = order?.status === "pending_payment";
  const isFailed = order?.status === "failed";
  const progress = order?.provision_progress ?? (isPending ? 0 : 5);
  const stepLabel =
    order?.provision_label || (isPending ? "Aguardando pagamento" : "Preparando...");
  const hasPix = Boolean(order?.pix_br_code);

  const isRenew = order?.order_type === "renewal" || isRenewFlow;

  const title = useMemo(() => {
    if (isFailed) return isRenew ? "Falha na renovação" : "Falha ao publicar o site";
    if (isProvisioning) return isRenew ? "Aplicando renovação" : "Publicando seu site";
    if (order?.status === "active") return isRenew ? "Renovação concluída" : "Site pronto";
    return "Pague com Pix";
  }, [isFailed, isProvisioning, isRenew, order?.status]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    if (!orderId) {
      setError("Pedido inválido");
      return;
    }

    let cancelled = false;
    const poll = async () => {
      try {
        let o = await api.webOrder(orderId);
        if (o.status === "pending_payment") {
          o = await api.syncWebOrderPayment(orderId);
        }
        if (cancelled) return;
        setOrder(o);
        if (o.status === "pending_payment" && o.pix_br_code && !pixAutoOpened.current) {
          pixAutoOpened.current = true;
          setPixOpen(true);
        }
        if (o.status === "active") {
          const targetSite = o.target_site_id ?? (Number.isFinite(siteId) ? siteId : null);
          const dest =
            (o.order_type === "renewal" || isRenewFlow) && targetSite
              ? `/dashboard/sites/${targetSite}?tab=billing`
              : "/dashboard/sites";
          setTimeout(() => router.push(dest), 1500);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Erro");
      }
    };

    void poll();
    const interval = setInterval(poll, isPending ? 4000 : 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [orderId, router, isPending, isRenewFlow, siteId]);

  useEffect(() => {
    if (!isPending) setPixOpen(false);
  }, [isPending]);

  const refreshPix = async () => {
    setPixRefreshing(true);
    try {
      const o = await api.retryWebCheckout(orderId);
      setOrder(o);
      setPixOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível gerar um novo Pix");
    } finally {
      setPixRefreshing(false);
    }
  };

  return (
    <PageShell>
      <div className="glass-card p-8 sm:p-10 text-center max-w-lg mx-auto">
        {isFailed ? (
          <SvgWarning className="w-12 h-12 mx-auto text-red-400 mb-4" />
        ) : (
          <SvgClock className="w-12 h-12 mx-auto text-[var(--accent)] mb-4" />
        )}

        <h1 className="text-2xl font-bold mb-2">{title}</h1>
        <p className="text-[var(--text-secondary)] text-sm mb-6">
          {isPending
            ? "Escaneie o QR Code ou copie o código Pix. Depois de pagar, a confirmação é automática."
            : stepLabel}
        </p>

        {!isFailed && !error && (
          <div className="mb-4">
            <ProgressBar value={progress} />
          </div>
        )}

        {isPending && hasPix && !pixOpen && (
          <div className="mb-4">
            <PixPayButton onClick={() => setPixOpen(true)} />
          </div>
        )}

        {order?.site_slug && (
          <p className="text-sm text-[var(--text-secondary)] mb-4">
            Link personalizado:{" "}
            <strong className="text-[var(--text-primary)]">{order.site_slug}</strong>
          </p>
        )}

        {order?.error_message && <p className="text-sm text-red-400 mb-4">{order.error_message}</p>}
        {error && <p className="text-sm text-red-400 mb-4">{error}</p>}

        <div className="flex flex-col gap-2 mt-6">
          {order?.status === "active" && (
            <Link href="/dashboard/sites" className="btn-primary">
              Ir para meus sites
            </Link>
          )}
          <Link href="/dashboard/sites" className="btn-ghost text-sm">
            Painel de sites
          </Link>
        </div>
      </div>

      <PixPaymentModal
        open={pixOpen && isPending}
        onClose={() => setPixOpen(false)}
        brCode={order?.pix_br_code ?? null}
        qrBase64={order?.pix_qr_base64 ?? null}
        amountCents={order?.total_cents}
        expiresAt={order?.pix_expires_at}
        onRefresh={refreshPix}
        refreshing={pixRefreshing}
      />
    </PageShell>
  );
}

export default function WebOrderCompletePage() {
  return (
    <Suspense
      fallback={
        <PageShell>
          <div className="text-center py-20">Carregando...</div>
        </PageShell>
      }
    >
      <WebOrderCompleteContent />
    </Suspense>
  );
}
