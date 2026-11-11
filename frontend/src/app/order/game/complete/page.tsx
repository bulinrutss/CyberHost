"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { PixPayButton, PixPaymentModal } from "@/components/PixPaymentModal";
import { PageShell } from "@/components/ui/PageShell";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SvgClock, SvgWarning } from "@/components/ui/svgs";
import { api, getToken, type GameOrder } from "@/lib/api";
import { gameProvisionStepLabel } from "@/lib/gameProvisionLabels";

const PROVISIONING = new Set(["paid", "provisioning"]);

function GameOrderCompleteContent() {
  const router = useRouter();
  const params = useSearchParams();
  const orderId = Number(params.get("order"));
  const [order, setOrder] = useState<GameOrder | null>(null);
  const [error, setError] = useState("");
  const [pixOpen, setPixOpen] = useState(false);
  const [pixRefreshing, setPixRefreshing] = useState(false);
  const pixAutoOpened = useRef(false);

  const isProvisioning = order ? PROVISIONING.has(order.status) : false;
  const isPending = order?.status === "pending_payment";
  const isFailed = order?.status === "failed";
  const progress = order?.provision_progress ?? (isPending ? 0 : 5);
  const stepLabel =
    order?.provision_label ||
    gameProvisionStepLabel(order?.provision_step) ||
    (isPending ? "Aguardando pagamento" : "Preparando...");
  const hasPix = Boolean(order?.pix_br_code);

  const title = useMemo(() => {
    if (isFailed) return "Falha ao criar servidor";
    if (isProvisioning) return "Criando seu servidor de jogo";
    if (order?.status === "active") return "Servidor pronto";
    return "Pague com Pix";
  }, [isFailed, isProvisioning, order?.status]);

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
        let o = await api.gameOrder(orderId);
        if (o.status === "pending_payment") {
          o = await api.syncGameOrderPayment(orderId);
        }
        if (cancelled) return;
        setOrder(o);
        if (o.status === "pending_payment" && o.pix_br_code && !pixAutoOpened.current) {
          pixAutoOpened.current = true;
          setPixOpen(true);
        }
        if (o.status === "active") {
          setTimeout(() => router.push("/dashboard/games"), 1500);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Erro");
      }
    };

    poll();
    const interval = setInterval(poll, isPending ? 4000 : 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [orderId, router, isPending]);

  useEffect(() => {
    if (!isPending) setPixOpen(false);
  }, [isPending]);

  const refreshPix = async () => {
    setPixRefreshing(true);
    try {
      const o = await api.retryGameCheckout(orderId);
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

        {order?.server_name && (
          <p className="text-sm font-mono text-muted mb-4">{order.server_name}</p>
        )}

        {order?.error_message && (
          <p className="text-sm text-red-400 mb-4">{order.error_message}</p>
        )}
        {error && <p className="text-sm text-red-400 mb-4">{error}</p>}

        <div className="flex flex-col gap-2 mt-6">
          {order?.status === "active" && (
            <Link href="/dashboard/games" className="btn-primary">
              Ir para meus servidores de jogo
            </Link>
          )}
          <Link href="/dashboard/games" className="btn-ghost text-sm">
            Painel de jogos
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

export default function GameOrderCompletePage() {
  return (
    <Suspense fallback={<PageShell><div className="text-center py-20">Carregando...</div></PageShell>}>
      <GameOrderCompleteContent />
    </Suspense>
  );
}
