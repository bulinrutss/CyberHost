"use client";

import { useCallback, useEffect, useState } from "react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { PageLoader } from "@/components/PageLoader";
import { FinanceAgenda } from "@/components/finance/FinanceAgenda";
import { FinanceAuth } from "@/components/finance/FinanceAuth";
import { FinanceGoals } from "@/components/finance/FinanceGoals";
import { FinancePwa } from "@/components/finance/FinancePwa";
import { FinanceLedger } from "@/components/finance/FinanceLedger";
import { FinanceStatsPanel } from "@/components/finance/FinanceStats";
import {
  SvgCalendar,
  SvgTrendingDown,
  SvgTrendingUp,
  SvgWallet,
} from "@/components/ui/svgs";
import {
  api,
  formatPrice,
  type FinanceEventItem,
  type FinanceGoal,
  type FinanceMeta,
  type FinanceStats,
  type User,
} from "@/lib/api";
import {
  clearFinanceToken,
  getFinanceToken,
  setFinanceToken,
} from "@/lib/financeSession";

type Tab = "overview" | "ledger" | "goals" | "agenda" | "stats";

const TABS: { id: Tab; label: string; short: string }[] = [
  { id: "overview", label: "Resumo", short: "Resumo" },
  { id: "ledger", label: "Lançamentos", short: "Fluxo" },
  { id: "goals", label: "Metas", short: "Metas" },
  { id: "agenda", label: "Agenda", short: "Agenda" },
  { id: "stats", label: "Estatísticas", short: "Métricas" },
];

export function FinanceApp() {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [meta, setMeta] = useState<FinanceMeta | null>(null);
  const [stats, setStats] = useState<FinanceStats | null>(null);
  const [events, setEvents] = useState<FinanceEventItem[]>([]);
  const [goals, setGoals] = useState<FinanceGoal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const bootstrap = useCallback(async () => {
    if (!getFinanceToken()) {
      setUser(null);
      setReady(true);
      return;
    }
    try {
      const me = await api.financeMe();
      setUser(me);
    } catch {
      clearFinanceToken();
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  const loadData = useCallback(async () => {
    if (!getFinanceToken()) return;
    setLoading(true);
    setError("");
    try {
      const [nextMeta, nextStats, nextEvents, nextGoals] = await Promise.all([
        api.financeMeta(),
        api.financeStats(6),
        api.financeEvents(),
        api.financeGoals(),
      ]);
      setMeta(nextMeta);
      setStats(nextStats);
      setEvents(nextEvents);
      setGoals(nextGoals);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar os dados");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  const logout = async () => {
    try {
      await api.financeLogout();
    } catch {
      /* cookie may already be gone */
    }
    clearFinanceToken();
    setUser(null);
    setStats(null);
    setEvents([]);
    setGoals([]);
  };

  if (!ready) {
    return (
      <div className="page-bg min-h-screen">
        <div className="relative z-10 max-w-3xl mx-auto px-4 py-24">
          <PageLoader label="Abrindo o financeiro…" />
        </div>
      </div>
    );
  }

  return (
    <div className="page-bg min-h-screen">
      <header className="glass-nav">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-[72px] flex items-center gap-4">
          <a href="/financeiro" className="inline-flex items-center gap-2.5 shrink-0">
            <span className="w-9 h-9 rounded-xl grid place-items-center bg-[var(--accent)] text-white">
              <SvgWallet className="w-5 h-5" />
            </span>
            <span className="leading-tight">
              <span className="block text-sm font-bold tracking-tight">Financeiro</span>
              <span className="block text-[11px] text-muted">ruts.dev</span>
            </span>
          </a>
          {user && (
            <nav className="hidden sm:flex items-center gap-1 flex-1 min-w-0 overflow-x-auto" aria-label="Financeiro">
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    tab === item.id
                      ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                      : "text-[var(--text-secondary)] hover:text-[var(--accent)]"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </nav>
          )}
          <div className="flex items-center gap-2 ml-auto">
            <FinancePwa />
            <ThemeToggle />
            {user && (
              <button type="button" className="btn-ghost !py-2 text-sm" onClick={logout}>
                Sair
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
        {!user ? (
          <FinanceAuth onDone={bootstrap} />
        ) : (
          <>
            {user && (
              <div className="sm:hidden flex gap-1 mb-6 overflow-x-auto">
                {TABS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setTab(item.id)}
                    className={`fin-chip shrink-0 ${tab === item.id ? "active" : ""}`}
                  >
                    {item.short}
                  </button>
                ))}
              </div>
            )}
            {error && (
              <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-3 mb-6">{error}</p>
            )}
            {loading && !stats ? (
              <PageLoader label="Carregando seus dados…" />
            ) : (
              <>
                {tab === "overview" && stats && (
                  <Overview
                    user={user}
                    stats={stats}
                    goals={goals}
                    onLedger={() => setTab("ledger")}
                    onAgenda={() => setTab("agenda")}
                    onGoals={() => setTab("goals")}
                  />
                )}
                {tab === "ledger" && <FinanceLedger meta={meta} onChanged={loadData} />}
                {tab === "goals" && <FinanceGoals goals={goals} onChanged={loadData} />}
                {tab === "agenda" && (
                  <FinanceAgenda
                    events={events}
                    categories={meta?.event_categories || []}
                    vapidPublicKey={meta?.vapid_public_key}
                    onChanged={loadData}
                  />
                )}
                {tab === "stats" && stats && <FinanceStatsPanel stats={stats} />}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Overview({
  user,
  stats,
  goals,
  onLedger,
  onAgenda,
  onGoals,
}: {
  user: User;
  stats: FinanceStats;
  goals: FinanceGoal[];
  onLedger: () => void;
  onAgenda: () => void;
  onGoals: () => void;
}) {
  const first = user.name.trim().split(/\s+/)[0] || "olá";
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Olá, {first}</h1>
        <p className="text-secondary mt-1">Acompanhe o fluxo de {stats.month_label.toLowerCase()}.</p>
      </div>
      <div className="grid sm:grid-cols-3 gap-4">
        <button type="button" className="glass-card p-5 text-left hover:border-[var(--accent)] transition-colors" onClick={onLedger}>
          <p className="text-xs text-muted inline-flex items-center gap-1.5">
            <SvgTrendingUp className="w-4 h-4 text-[var(--success)]" /> Entradas
          </p>
          <p className="text-2xl font-bold mt-2 tabular-nums text-[var(--success)]">{formatPrice(stats.income_cents)}</p>
        </button>
        <button type="button" className="glass-card p-5 text-left hover:border-[var(--accent)] transition-colors" onClick={onLedger}>
          <p className="text-xs text-muted inline-flex items-center gap-1.5">
            <SvgTrendingDown className="w-4 h-4 text-[var(--danger)]" /> Saídas
          </p>
          <p className="text-2xl font-bold mt-2 tabular-nums text-[var(--danger)]">{formatPrice(stats.expense_cents)}</p>
        </button>
        <div className="glass-card p-5">
          <p className="text-xs text-muted inline-flex items-center gap-1.5">
            <SvgWallet className="w-4 h-4 text-[var(--accent)]" /> Saldo do mês
          </p>
          <p
            className={`text-2xl font-bold mt-2 tabular-nums ${
              stats.balance_cents >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"
            }`}
          >
            {formatPrice(stats.balance_cents)}
          </p>
        </div>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">Próximos na agenda</h2>
            <button type="button" className="text-sm text-[var(--accent)] font-medium" onClick={onAgenda}>
              Ver agenda
            </button>
          </div>
          {stats.upcoming_events.length === 0 ? (
            <p className="text-sm text-muted">Nenhum compromisso nos próximos 14 dias.</p>
          ) : (
            <ul className="space-y-3">
              {stats.upcoming_events.slice(0, 5).map((event) => (
                <li key={event.id} className="flex items-start gap-3">
                  <span className="mt-0.5 text-[var(--accent)]">
                    <SvgCalendar className="w-4 h-4" />
                  </span>
                  <div className="min-w-0">
                    <p className="font-medium truncate">{event.title}</p>
                    <p className="text-xs text-muted">
                      {new Date(event.starts_at).toLocaleString("pt-BR", {
                        day: "2-digit",
                        month: "short",
                        hour: event.all_day ? undefined : "2-digit",
                        minute: event.all_day ? undefined : "2-digit",
                      })}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">Metas de poupança</h2>
            <button type="button" className="text-sm text-[var(--accent)] font-medium" onClick={onGoals}>
              Ver metas
            </button>
          </div>
          {goals.length === 0 ? (
            <p className="text-sm text-muted">Crie uma meta para acompanhar quanto falta juntar.</p>
          ) : (
            <ul className="space-y-3">
              {goals.slice(0, 3).map((goal) => (
                <li key={goal.id}>
                  <div className="flex justify-between text-sm gap-3 mb-1">
                    <span className="truncate font-medium">{goal.title}</span>
                    <span className="tabular-nums text-muted">{goal.progress_percent}%</span>
                  </div>
                  <p className="text-[11px] text-muted mb-1">
                    {goal.kind === "monthly" && goal.due_day
                      ? `Mensal · dia ${goal.due_day}`
                      : goal.due_on || goal.deadline
                        ? `Até ${new Date(`${goal.due_on || goal.deadline}T12:00:00`).toLocaleDateString("pt-BR")}`
                        : "Poupança"}
                  </p>
                  <div className="metric-bar-track">
                    <div className="metric-bar-fill" style={{ width: `${Math.max(goal.progress_percent, 3)}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="glass-card p-5">
          <h2 className="font-semibold mb-4">Categorias do mês</h2>
          {stats.by_category.length === 0 ? (
            <p className="text-sm text-muted">Cadastre gastos e entradas para ver o recorte.</p>
          ) : (
            <ul className="space-y-2">
              {stats.by_category.slice(0, 6).map((row) => (
                <li key={`${row.kind}-${row.id}`} className="flex justify-between text-sm gap-3">
                  <span className="text-secondary truncate">{row.label}</span>
                  <span
                    className={`tabular-nums font-medium ${
                      row.kind === "income" ? "text-[var(--success)]" : "text-[var(--danger)]"
                    }`}
                  >
                    {formatPrice(row.amount_cents)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
