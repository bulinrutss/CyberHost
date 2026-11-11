"use client";

import { formatPrice, type FinanceStats } from "@/lib/api";
import { formatTime } from "@/lib/finance";

export function FinanceStatsPanel({ stats }: { stats: FinanceStats }) {
  const maxBar = Math.max(
    1,
    ...stats.months.map((month) => Math.max(month.income_cents, month.expense_cents))
  );
  const expenseCats = stats.by_category.filter((row) => row.kind === "expense");
  const incomeCats = stats.by_category.filter((row) => row.kind === "income");
  const maxCat = Math.max(1, ...stats.by_category.map((row) => row.amount_cents));

  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-3 gap-4">
        <StatCard label="Entradas do mês" value={formatPrice(stats.income_cents)} tone="ok" />
        <StatCard label="Saídas do mês" value={formatPrice(stats.expense_cents)} tone="bad" />
        <StatCard
          label="Saldo do mês"
          value={formatPrice(stats.balance_cents)}
          tone={stats.balance_cents >= 0 ? "ok" : "bad"}
        />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="glass-card p-5">
          <h3 className="font-semibold mb-1">Fluxo nos últimos meses</h3>
          <p className="text-xs text-muted mb-5">Comparativo de entradas e saídas</p>
          <div className="flex items-end gap-3 h-44">
            {stats.months.map((month) => (
              <div key={`${month.year}-${month.month}`} className="flex-1 flex flex-col items-center gap-2 min-w-0">
                <div className="w-full flex items-end justify-center gap-1 h-32">
                  <div
                    className="w-[42%] rounded-t-md bg-[var(--accent)]"
                    style={{ height: `${Math.max((month.income_cents / maxBar) * 100, month.income_cents ? 4 : 0)}%` }}
                    title={`Entradas ${formatPrice(month.income_cents)}`}
                  />
                  <div
                    className="w-[42%] rounded-t-md bg-[var(--danger)]/80"
                    style={{ height: `${Math.max((month.expense_cents / maxBar) * 100, month.expense_cents ? 4 : 0)}%` }}
                    title={`Saídas ${formatPrice(month.expense_cents)}`}
                  />
                </div>
                <span className="text-[11px] text-muted truncate w-full text-center">{month.label}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-4 mt-4 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-[var(--accent)]" /> Entradas
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-[var(--danger)]/80" /> Saídas
            </span>
          </div>
        </div>
        <div className="glass-card p-5">
          <h3 className="font-semibold mb-1">Categorias em {stats.month_label}</h3>
          <p className="text-xs text-muted mb-4">Onde o dinheiro entra e sai</p>
          <div className="space-y-3">
            {stats.by_category.length === 0 && <p className="text-sm text-muted">Sem lançamentos neste mês.</p>}
            {expenseCats.map((row) => (
              <CatBar key={`e-${row.id}`} label={row.label} cents={row.amount_cents} max={maxCat} kind="expense" />
            ))}
            {incomeCats.map((row) => (
              <CatBar key={`i-${row.id}`} label={row.label} cents={row.amount_cents} max={maxCat} kind="income" />
            ))}
          </div>
        </div>
      </div>
      <div className="grid sm:grid-cols-3 gap-4">
        <div className="glass-card p-5">
          <p className="text-xs text-muted">Saldo acumulado</p>
          <p className="text-2xl font-bold mt-1 tabular-nums">{formatPrice(stats.all_time_balance_cents)}</p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-muted">Média diária de gastos</p>
          <p className="text-2xl font-bold mt-1 tabular-nums">{formatPrice(stats.avg_daily_expense_cents)}</p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-muted">Lançamentos no mês</p>
          <p className="text-2xl font-bold mt-1 tabular-nums">{stats.transaction_count}</p>
        </div>
      </div>
      <div className="glass-card p-5">
        <h3 className="font-semibold mb-3">Próximos eventos</h3>
        {stats.upcoming_events.length === 0 ? (
          <p className="text-sm text-muted">Nada nos próximos 14 dias.</p>
        ) : (
          <ul className="space-y-2">
            {stats.upcoming_events.map((event) => (
              <li key={event.id} className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium truncate">{event.title}</span>
                <span className="text-muted shrink-0">
                  {new Date(event.starts_at).toLocaleDateString("pt-BR")}
                  {event.all_day ? "" : ` · ${formatTime(event.starts_at)}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: string; tone: "ok" | "bad" }) {
  return (
    <div className="glass-card p-5">
      <p className="text-xs text-muted">{label}</p>
      <p className={`text-2xl font-bold mt-1 tabular-nums ${tone === "ok" ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
        {value}
      </p>
    </div>
  );
}

function CatBar({
  label,
  cents,
  max,
  kind,
}: {
  label: string;
  cents: number;
  max: number;
  kind: "income" | "expense";
}) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-secondary">{label}</span>
        <span className="tabular-nums font-medium">{formatPrice(cents)}</span>
      </div>
      <div className="metric-bar-track">
        <div
          className="metric-bar-fill"
          style={{
            width: `${Math.max((cents / max) * 100, 4)}%`,
            background:
              kind === "income"
                ? "linear-gradient(90deg, var(--accent), var(--accent-dark))"
                : "linear-gradient(90deg, var(--danger), #c53030)",
          }}
        />
      </div>
    </div>
  );
}
