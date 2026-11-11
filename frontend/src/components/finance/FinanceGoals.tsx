"use client";

import { useEffect, useMemo, useState } from "react";
import { BusyLabel } from "@/components/PageLoader";
import { SvgPlus, SvgTrash, SvgWallet } from "@/components/ui/svgs";
import { api, formatPrice, type FinanceGoal, type FinanceGoalKind } from "@/lib/api";
import { centsToInput, parseBRLToCents, todayISODate } from "@/lib/finance";

export function FinanceGoals({ goals, onChanged }: { goals: FinanceGoal[]; onChanged: () => void }) {
  const [editing, setEditing] = useState<FinanceGoal | "new" | null>(null);
  const [depositing, setDepositing] = useState<FinanceGoal | null>(null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Metas</h1>
          <p className="text-sm text-secondary mt-0.5">
            Meta mensal com dia de conclusão, ou poupança com prazo livre.
          </p>
        </div>
        <button type="button" className="btn-primary !py-2 !px-4 text-sm" onClick={() => setEditing("new")}>
          <SvgPlus className="w-4 h-4" />
          Nova meta
        </button>
      </div>
      {goals.length === 0 ? (
        <div className="glass-card p-8 text-center text-sm text-muted">
          Nenhuma meta ainda. Crie uma mensal (ex.: guardar até o dia 10) ou uma poupança de longo prazo.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {goals.map((goal) => (
            <article key={goal.id} className="glass-card p-5 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold truncate">{goal.title}</h3>
                    <span className="fin-chip !py-0.5 !px-2 text-[11px] active">
                      {goal.kind === "monthly" ? "Mensal" : "Poupança"}
                    </span>
                  </div>
                  <p className="text-xs text-muted mt-1">{dueCopy(goal)}</p>
                </div>
                <span className="text-sm font-semibold text-[var(--accent)] tabular-nums">
                  {goal.progress_percent}%
                </span>
              </div>
              <div className="metric-bar-track h-2">
                <div className="metric-bar-fill" style={{ width: `${Math.max(goal.progress_percent, 3)}%` }} />
              </div>
              <p className="text-sm text-secondary">
                {formatPrice(goal.saved_cents)} de {formatPrice(goal.target_cents)}
                {goal.remaining_cents > 0 ? ` · faltam ${formatPrice(goal.remaining_cents)}` : " · meta atingida"}
              </p>
              {goal.notes && <p className="text-xs text-muted line-clamp-2">{goal.notes}</p>}
              <div className="flex gap-2">
                <button type="button" className="btn-primary !py-1.5 !px-3 text-xs" onClick={() => setDepositing(goal)}>
                  Guardar
                </button>
                <button type="button" className="btn-ghost !py-1.5 !px-3 text-xs" onClick={() => setEditing(goal)}>
                  Editar
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {editing && (
        <GoalModal
          goal={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
      {depositing && (
        <DepositModal
          goal={depositing}
          onClose={() => setDepositing(null)}
          onSaved={() => {
            setDepositing(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function dueCopy(goal: FinanceGoal): string {
  if (goal.kind === "monthly" && goal.due_day) {
    const dateLabel = goal.due_on
      ? new Date(`${goal.due_on}T12:00:00`).toLocaleDateString("pt-BR")
      : `dia ${goal.due_day}`;
    if (goal.days_left == null) return `Concluir até o dia ${goal.due_day} de cada mês`;
    if (goal.days_left < 0) return `Venceu em ${dateLabel}`;
    if (goal.days_left === 0) return `Concluir hoje (dia ${goal.due_day})`;
    return `Concluir até ${dateLabel} · ${goal.days_left} dia${goal.days_left === 1 ? "" : "s"}`;
  }
  if (goal.due_on || goal.deadline) {
    const iso = goal.due_on || goal.deadline;
    const label = new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR");
    if (goal.days_left == null) return `Concluir em ${label}`;
    if (goal.days_left < 0) return `Venceu em ${label}`;
    if (goal.days_left === 0) return "Concluir hoje";
    return `Concluir em ${label} · ${goal.days_left} dia${goal.days_left === 1 ? "" : "s"}`;
  }
  return "Sem dia de conclusão";
}

function GoalModal({
  goal,
  onClose,
  onSaved,
}: {
  goal: FinanceGoal | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const initial = useMemo(
    () => ({
      title: goal?.title || "",
      kind: (goal?.kind || "monthly") as FinanceGoalKind,
      target: goal ? centsToInput(goal.target_cents) : "",
      saved: goal ? centsToInput(goal.saved_cents) : "0,00",
      due_day: String(goal?.due_day || new Date().getDate()),
      deadline: goal?.deadline || "",
      notes: goal?.notes || "",
    }),
    [goal]
  );
  const [form, setForm] = useState(initial);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => setForm(initial), [initial]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const target_cents = parseBRLToCents(form.target);
    const savedParsed = form.saved.trim() ? parseBRLToCents(form.saved) : 0;
    if (!target_cents) {
      setError("Informe o valor da meta, por exemplo 5.000,00");
      return;
    }
    const due_day = Number(form.due_day);
    if (form.kind === "monthly" && (!Number.isInteger(due_day) || due_day < 1 || due_day > 31)) {
      setError("Escolha o dia do mês para concluir a meta");
      return;
    }
    if (form.kind === "savings" && !form.deadline) {
      setError("Escolha o dia para concluir a meta");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = {
        title: form.title.trim(),
        kind: form.kind,
        target_cents,
        saved_cents: savedParsed || 0,
        due_day: form.kind === "monthly" ? due_day : null,
        deadline: form.kind === "savings" ? form.deadline || null : null,
        notes: form.notes.trim(),
      };
      if (goal) await api.financeUpdateGoal(goal.id, payload);
      else await api.financeCreateGoal(payload);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setLoading(false);
    }
  };

  const remove = async () => {
    if (!goal) return;
    setLoading(true);
    try {
      await api.financeDeleteGoal(goal.id);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir");
      setLoading(false);
    }
  };

  return (
    <div className="fin-modal-backdrop" onClick={onClose} role="presentation">
      <form className="glass-card fin-modal" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h2 className="text-lg font-semibold mb-4">{goal ? "Editar meta" : "Nova meta"}</h2>
        <div className="space-y-4">
          <div>
            <label className="text-xs text-muted block mb-1.5">Nome da meta</label>
            <input
              required
              className="input-glass"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Reserva, viagem, emergência…"
            />
          </div>
          <div className="flex gap-2">
            {(
              [
                ["monthly", "Meta mensal"],
                ["savings", "Poupança"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`fin-chip flex-1 justify-center ${form.kind === id ? "active" : ""}`}
                onClick={() => setForm({ ...form, kind: id })}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-muted block mb-1.5">Quanto juntar (R$)</label>
              <input
                required
                inputMode="decimal"
                className="input-glass"
                value={form.target}
                onChange={(e) => setForm({ ...form, target: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted block mb-1.5">Já guardado (R$)</label>
              <input
                inputMode="decimal"
                className="input-glass"
                value={form.saved}
                onChange={(e) => setForm({ ...form, saved: e.target.value })}
              />
            </div>
          </div>
          {form.kind === "monthly" ? (
            <div>
              <label className="text-xs text-muted block mb-1.5">Dia para concluir a meta</label>
              <select
                required
                className="input-glass"
                value={form.due_day}
                onChange={(e) => setForm({ ...form, due_day: e.target.value })}
              >
                {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => (
                  <option key={day} value={String(day)}>
                    Dia {day} de cada mês
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-muted mt-1">
                O progresso zera no mês seguinte. Em fevereiro, o dia 31 vira o último dia do mês.
              </p>
            </div>
          ) : (
            <div>
              <label className="text-xs text-muted block mb-1.5">Dia para concluir a meta</label>
              <input
                type="date"
                required
                min={todayISODate()}
                className="input-glass"
                value={form.deadline}
                onChange={(e) => setForm({ ...form, deadline: e.target.value })}
              />
            </div>
          )}
          <div>
            <label className="text-xs text-muted block mb-1.5">Notas</label>
            <textarea
              className="input-glass min-h-[80px] resize-y"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
          {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
        </div>
        <div className="flex flex-wrap justify-between gap-2 mt-6">
          {goal ? (
            <button type="button" className="btn-ghost text-[var(--danger)]" onClick={remove} disabled={loading}>
              <SvgTrash className="w-4 h-4" />
              Excluir
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2 ml-auto">
            <button type="button" className="btn-ghost" onClick={onClose}>
              Cancelar
            </button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? <BusyLabel>Salvando…</BusyLabel> : "Salvar"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

function DepositModal({
  goal,
  onClose,
  onSaved,
}: {
  goal: FinanceGoal;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const cents = parseBRLToCents(amount);
    if (!cents) {
      setError("Informe quanto vai guardar agora");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.financeDepositGoal(goal.id, cents);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível guardar");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fin-modal-backdrop" onClick={onClose} role="presentation">
      <form className="glass-card fin-modal" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <div className="flex items-center gap-2 mb-4">
          <SvgWallet className="w-5 h-5 text-[var(--accent)]" />
          <h2 className="text-lg font-semibold">Guardar em {goal.title}</h2>
        </div>
        <p className="text-sm text-secondary mb-4">
          Já tem {formatPrice(goal.saved_cents)} de {formatPrice(goal.target_cents)}.
        </p>
        <label className="text-xs text-muted block mb-1.5">Valor a guardar (R$)</label>
        <input
          required
          autoFocus
          inputMode="decimal"
          className="input-glass"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="200,00"
        />
        {error && <p className="text-sm text-[var(--danger)] mt-3">{error}</p>}
        <div className="flex justify-end gap-2 mt-6">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? <BusyLabel>Guardando…</BusyLabel> : "Guardar"}
          </button>
        </div>
      </form>
    </div>
  );
}
