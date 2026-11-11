"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { WebSiteCard } from "@/components/WebSiteCard";
import { SvgGlobe, SvgPlus } from "@/components/ui/svgs";
import { api, type WebSite } from "@/lib/api";

export default function WebSitesDashboardPage() {
  const router = useRouter();
  const [sites, setSites] = useState<WebSite[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const list = await api.webSites();
      setSites(list);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const hasProvisioning = sites.some((s) => s.is_provisioning);
    const interval = setInterval(() => void load(), hasProvisioning ? 2000 : 10000);
    return () => clearInterval(interval);
  }, [sites]);

  const online = sites.filter((s) => s.status === "running").length;

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-10">
        <div>
          <p className="text-sm font-medium text-[var(--accent)] mb-2 tracking-wide uppercase">
            Sites
          </p>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">Hospedagem de sites</h1>
          <p className="text-secondary mt-2 max-w-lg">
            Sites online com link personalizado. Envie arquivos, ligue e desligue quando quiser — domínio próprio no
            painel, em poucos cliques.
          </p>
        </div>
        <button onClick={() => router.push("/order/web")} className="btn-primary shrink-0">
          <SvgPlus className="w-4 h-4" />
          Novo site
        </button>
      </div>

      {!loading && sites.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8">
          {[
            { label: "Total", value: sites.length },
            { label: "Online", value: online },
            { label: "Parados", value: sites.length - online },
          ].map((s) => (
            <div key={s.label} className="glass-card p-4 text-center">
              <p className="text-xs text-muted uppercase tracking-wider">{s.label}</p>
              <p className="text-2xl font-bold mt-1">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="grid md:grid-cols-2 gap-5">
          {[1, 2].map((i) => (
            <div key={i} className="glass-card p-6 h-64 shimmer rounded-2xl" />
          ))}
        </div>
      ) : sites.length === 0 ? (
        <div className="glass-card text-center py-20 px-6">
          <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-brand-400/20 to-brand-600/20 flex items-center justify-center">
            <SvgGlobe className="w-8 h-8 text-[var(--accent)]" />
          </div>
          <h2 className="text-xl font-semibold mb-2">Nenhum site ainda</h2>
          <p className="text-muted mb-6 max-w-md mx-auto">
            Contrate um plano e publique com link personalizado. Domínio próprio você configura depois, se quiser.
          </p>
          <button onClick={() => router.push("/order/web")} className="btn-primary">
            Contratar hospedagem
          </button>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-5">
          {sites.map((s) => (
            <WebSiteCard key={s.id} site={s} />
          ))}
        </div>
      )}
    </>
  );
}
