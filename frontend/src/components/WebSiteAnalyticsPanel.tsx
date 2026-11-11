"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { SvgRefresh } from "@/components/ui/svgs";
import { api, type WebSite, type WebSiteAnalytics } from "@/lib/api";

type Props = {
  site: WebSite;
  admin?: boolean;
};

const PERIODS = [7, 30, 90] as const;

function formatDayLabel(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

export function WebSiteAnalyticsPanel({ site, admin = false }: Props) {
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30);
  const [stats, setStats] = useState<WebSiteAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = admin
        ? await api.adminWebSiteAnalytics(site.id, days)
        : await api.webSiteAnalytics(site.id, days);
      setStats(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível carregar as estatísticas");
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, [admin, days, site.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const chartMax = useMemo(() => {
    if (!stats?.daily.length) return 1;
    return Math.max(
      1,
      ...stats.daily.map((row) => Math.max(row.page_views, row.link_clicks, row.unique_visitors))
    );
  }, [stats]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white">Estatísticas</h3>
          <p className="text-sm text-slate-400">
            Visualizações da página e cliques nos links publicados.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-white/10 p-0.5">
            {PERIODS.map((period) => (
              <button
                key={period}
                type="button"
                onClick={() => setDays(period)}
                className={
                  days === period
                    ? "rounded-md bg-cyan-500/20 px-3 py-1.5 text-xs font-medium text-cyan-200"
                    : "rounded-md px-3 py-1.5 text-xs text-slate-400 hover:text-white"
                }
              >
                {period} dias
              </button>
            ))}
          </div>
          <button type="button" onClick={() => void load()} className="btn-ghost !py-2" disabled={loading}>
            <SvgRefresh className="h-4 w-4" />
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      {loading && !stats ? (
        <p className="text-sm text-slate-400">Carregando estatísticas…</p>
      ) : null}

      {stats ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Visualizações" value={stats.page_views} hint="Aberturas da página" />
            <StatCard label="Cliques" value={stats.link_clicks} hint="Cliques nos links" />
            <StatCard label="Visitantes únicos" value={stats.unique_visitors} hint="Por dispositivo" />
            <StatCard
              label="Taxa de clique"
              value={`${stats.click_rate_pct.toFixed(1)}%`}
              hint="Cliques / visualizações"
            />
          </div>

          <section className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
            <h4 className="mb-4 text-sm font-medium text-slate-200">Atividade diária</h4>
            {stats.daily.every((row) => row.page_views === 0 && row.link_clicks === 0) ? (
              <p className="text-sm text-slate-500">
                Ainda não há dados neste período. Publique a página no criador e aguarde as primeiras
                visitas.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <div className="flex min-w-[640px] items-end gap-1.5">
                  {stats.daily.map((row) => {
                    const viewsH = Math.round((row.page_views / chartMax) * 72);
                    const clicksH = Math.round((row.link_clicks / chartMax) * 72);
                    return (
                      <div key={row.date} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                        <div className="flex h-20 w-full items-end justify-center gap-0.5">
                          <div
                            className="w-2 rounded-t bg-cyan-400/80"
                            style={{ height: `${Math.max(viewsH, row.page_views ? 4 : 0)}px` }}
                            title={`${row.page_views} visualizações`}
                          />
                          <div
                            className="w-2 rounded-t bg-violet-400/80"
                            style={{ height: `${Math.max(clicksH, row.link_clicks ? 4 : 0)}px` }}
                            title={`${row.link_clicks} cliques`}
                          />
                        </div>
                        <span className="truncate text-[10px] text-slate-500">{formatDayLabel(row.date)}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-3 flex gap-4 text-xs text-slate-400">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-sm bg-cyan-400/80" />
                    Visualizações
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-sm bg-violet-400/80" />
                    Cliques
                  </span>
                </div>
              </div>
            )}
          </section>

          <section className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
            <h4 className="mb-3 text-sm font-medium text-slate-200">Cliques por link</h4>
            {stats.links.length === 0 ? (
              <p className="text-sm text-slate-500">Nenhum link configurado no criador de página.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[320px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-slate-400">
                      <th className="py-2 pr-3 font-medium">Link</th>
                      <th className="py-2 text-right font-medium">Cliques</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.links.map((link) => (
                      <tr key={link.link_id} className="border-b border-white/5 last:border-0">
                        <td className="py-2.5 pr-3 text-white">{link.label || "Link"}</td>
                        <td className="py-2.5 text-right tabular-nums text-slate-200">{link.clicks}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: number | string; hint: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-white">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  );
}
