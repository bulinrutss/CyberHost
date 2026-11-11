"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  VpsPlanConfigurator,
  type OsTemplate,
  type Plan,
  type Preset,
  type QuoteResult,
} from "@/components/VpsPlanConfigurator";
import { PageLoader } from "@/components/PageLoader";

import { API_URL } from "@/lib/apiBase";

export function VpsPriceSimulator() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [osTemplates, setOsTemplates] = useState<OsTemplate[]>([]);

  useEffect(() => {
    fetch(`${API_URL}/api/vps/plans`)
      .then((r) => r.json())
      .then(setPlans)
      .catch(() => setPlans([]));
    fetch(`${API_URL}/api/vps/presets`)
      .then((r) => r.json())
      .then(setPresets)
      .catch(() => setPresets([]));
    fetch(`${API_URL}/api/vps/os-templates`)
      .then((r) => r.json())
      .then(setOsTemplates)
      .catch(() => setOsTemplates([]));
  }, []);

  const onQuote = useCallback(
    async (data: {
      plan_id: number;
      vcpu: number;
      ram_mb: number;
      disk_gb: number;
      preset_id: number | null;
      coupon_code?: string | null;
      os_template: string;
    }): Promise<QuoteResult> => {
      const res = await fetch(`${API_URL}/api/vps/quote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = err.detail;
        throw new Error(
          typeof detail === "string" ? detail : Array.isArray(detail) ? "Dados inválidos" : "Erro ao calcular"
        );
      }
      return res.json();
    },
    []
  );

  if (!plans.length) {
    return <PageLoader label="Carregando planos…" />;
  }

  return (
    <div>
      <VpsPlanConfigurator
        plans={plans}
        presets={presets}
        osTemplates={osTemplates}
        onQuote={onQuote}
        mode="simulator"
      />
      <div className="mt-8 text-center">
        <p className="text-sm text-[var(--text-secondary)] mb-4">
          Gostou do valor? Crie sua conta e contrate em minutos.
        </p>
        <Link href="/register" className="btn-primary !px-8 !py-3.5 inline-block">
          Criar conta e contratar
        </Link>
      </div>
    </div>
  );
}
