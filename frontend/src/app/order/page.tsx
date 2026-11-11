"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageShell } from "@/components/ui/PageShell";
import {
  VpsPlanConfigurator,
  type OsTemplate,
  type Plan,
  type Preset,
} from "@/components/VpsPlanConfigurator";
import { api, getToken } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

type OrderResponse = {
  id: number;
  status: string;
  payment_checkout_url: string | null;
};

export default function OrderPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [osTemplates, setOsTemplates] = useState<OsTemplate[]>([]);
  const [hostname, setHostname] = useState("");
  const [paymentsRequired, setPaymentsRequired] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.plans().then(setPlans);
    api.presets().then(setPresets);
    api.osTemplates().then(setOsTemplates);
    api.paymentConfig().then((c) => setPaymentsRequired(c.payments_required));
  }, [router]);

  const onQuote = useCallback(
    (data: {
      plan_id: number;
      vcpu: number;
      ram_mb: number;
      disk_gb: number;
      preset_id: number | null;
      coupon_code?: string | null;
      os_template: string;
    }) => api.quote(data),
    []
  );

  const submit = async (config: {
    plan_id: number;
    preset_id: number | null;
    vcpu: number;
    ram_mb: number;
    disk_gb: number;
    coupon_code?: string | null;
    os_template: string;
  }) => {
    if (!hostname.trim()) {
      setError("Informe o hostname");
      return;
    }
    if (
      hostname.trim().length < 3 ||
      hostname.trim().length > 63 ||
      !/^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$/.test(hostname.trim())
    ) {
      setError(
        "O hostname só pode ter letras sem acento, números e hífen. Não use espaços, ç, ã, é nem outros caracteres especiais. Exemplo: meu-servidor"
      );
      return;
    }
    setLoading(true);
    setError("");
    try {
      const order = (await api.createOrder({
        plan_id: config.plan_id,
        preset_id: config.preset_id ?? undefined,
        vcpu: config.vcpu,
        ram_mb: config.ram_mb,
        disk_gb: config.disk_gb,
        hostname,
        coupon_code: config.coupon_code ?? undefined,
        os_template: config.os_template,
      })) as OrderResponse;

      router.push(`/order/complete?order=${order.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar pedido");
    } finally {
      setLoading(false);
    }
  };

  if (!plans.length) {
    return (
      <PageShell>
        <div className="max-w-4xl mx-auto">
          <PageLoader label="Carregando planos…" />
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell wide>
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <p className="text-sm text-[var(--accent)] uppercase tracking-wide mb-2">Novo servidor</p>
          <h1 className="text-3xl font-bold tracking-tight">Configurar servidor</h1>
          <p className="text-secondary mt-2">
            Escolha um plano pronto ou personalize vCPU, RAM e disco NVMe.
          </p>
        </div>

        <VpsPlanConfigurator
          plans={plans}
          presets={presets}
          osTemplates={osTemplates}
          onQuote={onQuote}
          mode="order"
          hostname={hostname}
          onHostnameChange={setHostname}
          onSubmit={submit}
          loading={loading}
          error={error}
          paymentsRequired={paymentsRequired}
          submitLabel={paymentsRequired ? "Pagar com Pix" : "Criar servidor agora"}
        />
      </div>
    </PageShell>
  );
}
