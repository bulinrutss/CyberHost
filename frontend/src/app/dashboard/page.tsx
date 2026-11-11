"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { SvgPlus, SvgServer } from "@/components/ui/svgs";
import { VpsCard } from "@/components/VpsCard";
import { PageLoader } from "@/components/PageLoader";
import { api, type VpsInstanceList } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [instances, setInstances] = useState<VpsInstanceList[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const inst = await api.instances();
      setInstances(inst.filter((v) => v.status !== "deleted"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const hasProvisioning = instances.some((v) => v.is_provisioning);
    const interval = setInterval(load, hasProvisioning ? 2000 : 8000);
    return () => clearInterval(interval);
  }, [instances]);

  const online = instances.filter((v) => v.power_state === "poweredOn").length;

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-10">
        <div>
          <p className="text-sm font-medium text-[var(--accent)] mb-2 tracking-wide uppercase">
            CyberHost
          </p>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">Meus servidores</h1>
          <p className="text-secondary mt-2 max-w-lg">
            Monitore CPU, memória e disco em tempo real. Gerencie suas VPS com um clique.
          </p>
        </div>
        <button onClick={() => router.push("/order")} className="btn-primary shrink-0">
          <SvgPlus className="w-4 h-4" />
          Nova VPS
        </button>
      </div>

      {!loading && instances.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          {[
            { label: "Total", value: instances.length },
            { label: "Online", value: online },
            { label: "Offline", value: instances.length - online },
            {
              label: "vCPU total",
              value: instances.reduce((s, v) => s + v.vcpu, 0),
            },
          ].map((s) => (
            <div key={s.label} className="glass-card p-4 text-center">
              <p className="text-xs text-muted uppercase tracking-wider">{s.label}</p>
              <p className="text-2xl font-bold mt-1">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <PageLoader label="Carregando servidores…" />
      ) : instances.length === 0 ? (
        <div className="glass-card text-center py-20 px-6">
          <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-brand-400/20 to-brand-600/20 flex items-center justify-center">
            <SvgServer className="w-8 h-8 text-[var(--accent)]" />
          </div>
          <h2 className="text-xl font-semibold mb-2">Nenhum servidor ainda</h2>
          <p className="text-muted mb-6">
            Provisione sua primeira VPS Windows em minutos. Sua conta já inclui 20 GB no CyberCloud
            para arquivos.
          </p>
          <button onClick={() => router.push("/order")} className="btn-primary">
            Criar primeira VPS
          </button>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-5">
          {instances.map((vps) => (
            <VpsCard key={vps.id} vps={vps} />
          ))}
        </div>
      )}
    </>
  );
}
