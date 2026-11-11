"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type AdminAnalytics } from "@/lib/api";
import { InlineLoader } from "@/components/PageLoader";

type Days = 7 | 30 | 90;

function formatWhen(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(
    new Date(value)
  );
}

function formatDay(iso: string) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function formatHour(iso: string) {
  const hour = iso.slice(11, 13);
  return `${hour}h`;
}

function formatDuration(ms: number) {
  if (ms < 1000) return `${ms} ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest}s`;
}

function eventLabel(name: string) {
  if (name === "page_view") return "Página";
  if (name === "click") return "Clique";
  if (name === "form_submit") return "Formulário";
  if (name === "page_leave") return "Saída";
  return name;
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="glass-card p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="text-2xl font-semibold mt-1 tabular-nums">{value}</p>
      {hint ? <p className="text-xs text-muted mt-1">{hint}</p> : null}
    </div>
  );
}

function RankList({
  title,
  rows,
  empty,
}: {
  title: string;
  rows: AdminAnalytics["top_pages"];
  empty: string;
}) {
  const max = Math.max(1, ...rows.map((row) => row.count));
  return (
    <div className="glass-card p-5">
      <p className="font-medium mb-3">{title}</p>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.key}>
              <div className="flex justify-between gap-3 text-sm">
                <span className="truncate" title={row.key}>
                  {row.key}
                </span>
                <span className="tabular-nums text-muted shrink-0">
                  {row.count}
                  {row.unique ? ` · ${row.unique} vis.` : ""}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-[var(--ring-track)] mt-1 overflow-hidden">
                <div
                  className="h-full rounded-full bg-[var(--accent)]"
                  style={{ width: `${Math.max(6, (row.count / max) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AdminTrafficPanel({ days }: { days: Days }) {
  const [stats, setStats] = useState<AdminAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (window: Days) => {
    setLoading(true);
    setError("");
    try {
      setStats(await api.adminAnalytics(window));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível carregar os acessos");
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(days);
  }, [days, load]);

  if (loading && !stats) {
    return <InlineLoader label="Carregando acessos…" />;
  }
  if (error && !stats) {
    return <p className="text-red-400 text-sm">{error}</p>;
  }
  if (!stats) return null;

  const maxDay = Math.max(1, ...stats.daily.map((day) => day.page_views + day.clicks));
  const maxHour = Math.max(1, ...stats.hourly.map((hour) => hour.page_views + hour.clicks));

  return (
    <div className="space-y-5">
      {error ? <p className="text-xs text-red-400">{error}</p> : null}
      <p className="text-xs text-muted">
        Atualizado {formatWhen(stats.generated_at)} · visitas, cliques e formulários dos últimos{" "}
        {stats.days} dias. Senhas, PIX e tokens não são gravados.
      </p>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi label="Visualizações" value={String(stats.totals.page_views)} hint="páginas abertas" />
        <Kpi
          label="Visitantes"
          value={String(stats.totals.unique_visitors)}
          hint={`${stats.totals.unique_sessions} sessões`}
        />
        <Kpi label="Cliques" value={String(stats.totals.clicks)} hint={`${stats.totals.forms} envios de form`} />
        <Kpi
          label="Tempo médio"
          value={formatDuration(stats.totals.avg_duration_ms)}
          hint={`rolagem média ${stats.totals.avg_scroll_pct}%`}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Kpi label="Anônimos" value={String(stats.auth.anonymous)} hint="page views sem login" />
        <Kpi label="Clientes logados" value={String(stats.auth.logged_in)} />
        <Kpi
          label="Admins"
          value={String(stats.auth.admin)}
          hint={`${stats.totals.identified_users} contas distintas`}
        />
      </div>

      <div className="glass-card p-5">
        <p className="font-medium mb-3">Acessos por dia</p>
        <div className="overflow-x-auto">
          <div className="flex items-end gap-1 min-h-[140px]">
            {stats.daily.map((day) => {
              const total = day.page_views + day.clicks;
              const h = Math.max(4, (total / maxDay) * 120);
              return (
                <div key={day.date} className="flex-1 min-w-[10px] flex flex-col items-center gap-1">
                  <div
                    className="w-full rounded-t bg-[var(--accent)]"
                    style={{ height: `${h}px` }}
                    title={`${formatDay(day.date)} · ${day.page_views} views · ${day.clicks} cliques · ${day.visitors} vis.`}
                  />
                  <span className="text-[9px] text-muted">{formatDay(day.date)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="glass-card p-5">
        <p className="font-medium mb-3">Últimas 24 horas</p>
        <div className="flex items-end gap-px min-h-[90px] overflow-x-auto">
          {stats.hourly.map((hour) => {
            const total = hour.page_views + hour.clicks;
            const h = Math.max(2, (total / maxHour) * 72);
            return (
              <div key={hour.hour} className="flex-1 min-w-[6px] flex flex-col items-center">
                <div
                  className="w-full rounded-t bg-sky-400/80"
                  style={{ height: `${h}px` }}
                  title={`${formatHour(hour.hour)} · ${hour.page_views} views · ${hour.clicks} cliques`}
                />
              </div>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <RankList title="Páginas mais vistas" rows={stats.top_pages} empty="Ainda sem page views." />
        <RankList title="Entradas de sessão" rows={stats.top_entry} empty="Ainda sem sessões." />
        <RankList title="Cliques em botões" rows={stats.top_clicks} empty="Ainda sem cliques." />
        <RankList title="Formulários enviados" rows={stats.top_forms} empty="Ainda sem envios." />
        <RankList title="Navegadores" rows={stats.browsers} empty="—" />
        <RankList title="Sistemas" rows={stats.systems} empty="—" />
        <RankList title="Idiomas" rows={stats.languages} empty="—" />
        <RankList title="Origem" rows={stats.referrers} empty="—" />
        <RankList title="Dispositivo" rows={stats.viewports} empty="—" />
      </div>

      <div className="glass-card p-5">
        <p className="font-medium mb-3">Eventos recentes</p>
        {stats.recent.length === 0 ? (
          <p className="text-sm text-muted">Navegue o site para começar a coletar.</p>
        ) : (
          <div className="max-h-[360px] overflow-y-auto space-y-2">
            {stats.recent.map((event, index) => (
              <article
                key={`${event.at}-${event.path}-${index}`}
                className="rounded-xl border border-[var(--glass-border)] px-3 py-2 text-sm"
              >
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="font-medium">
                    {eventLabel(event.name)} · {event.path}
                  </p>
                  <span className="text-[11px] text-muted">{formatWhen(event.at)}</span>
                </div>
                <p className="text-xs text-secondary mt-0.5">
                  {event.label || "—"}
                  {event.user_name ? ` · ${event.user_name}` : " · visitante"}
                  {event.is_admin ? " · admin" : ""}
                </p>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
