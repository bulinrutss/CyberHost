"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BusyLabel } from "@/components/PageLoader";
import { SvgChevronLeft, SvgPlus, SvgTrash } from "@/components/ui/svgs";
import {
  api,
  formatPrice,
  type FinanceKind,
  type FinanceMeta,
  type FinanceTransaction,
  type FinanceTransactionPayload,
} from "@/lib/api";
import {
  addMonths,
  centsToInput,
  parseBRLToCents,
  periodBounds,
  signedPrice,
  todayISODate,
  transactionLabel,
  type FinancePeriodId,
} from "@/lib/finance";

type Props = {
  meta: FinanceMeta | null;
  onChanged: () => void;
};

const PERIODS: { id: FinancePeriodId; label: string }[] = [
  { id: "month", label: "Mês" },
  { id: "7d", label: "7 dias" },
  { id: "30d", label: "30 dias" },
  { id: "year", label: "Ano" },
  { id: "all", label: "Tudo" },
  { id: "custom", label: "Personalizado" },
];

export function FinanceLedger({ meta, onChanged }: Props) {
  const [period, setPeriod] = useState<FinancePeriodId>("month");
  const [monthCursor, setMonthCursor] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [kind, setKind] = useState<FinanceKind | "all">("all");
  const [category, setCategory] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<FinanceTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<FinanceTransaction | "new-income" | "new-expense" | null>(null);

  const bounds = useMemo(
    () => periodBounds(period, monthCursor, customStart, customEnd),
    [period, monthCursor, customStart, customEnd]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const list = await api.financeTransactions({
        start: bounds.start,
        end: bounds.end,
        kind: kind === "all" ? undefined : kind,
        category: category || undefined,
        payment_method: paymentMethod || undefined,
      });
      setRows(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar os lançamentos");
    } finally {
      setLoading(false);
    }
  }, [bounds.start, bounds.end, kind, category, paymentMethod]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setCategory("");
  }, [kind]);

  const catOptions =
    kind === "income" ? meta?.income_categories || [] : kind === "expense" ? meta?.expense_categories || [] : [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => {
      const cat = labelOf(meta, row.kind, row.category).toLowerCase();
      const method = labelMethod(meta, row.payment_method).toLowerCase();
      return (
        row.title.toLowerCase().includes(q) ||
        row.notes.toLowerCase().includes(q) ||
        cat.includes(q) ||
        method.includes(q)
      );
    });
  }, [rows, search, meta]);

  const totals = useMemo(() => {
    let income = 0;
    let expense = 0;
    for (const row of filtered) {
      if (row.kind === "income") income += row.amount_cents;
      else expense += row.amount_cents;
    }
    return { income, expense, balance: income - expense, count: filtered.length };
  }, [filtered]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Fluxo</h1>
          <p className="text-sm text-secondary mt-0.5">{bounds.label}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="fin-btn-income" onClick={() => setEditing("new-income")}>
            <SvgPlus className="w-4 h-4" />
            Adicionar entrada
          </button>
          <button type="button" className="fin-btn-expense" onClick={() => setEditing("new-expense")}>
            <SvgPlus className="w-4 h-4" />
            Adicionar gasto
          </button>
        </div>
      </div>

      <div className="glass-card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {PERIODS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`fin-chip ${period === item.id ? "active" : ""}`}
              onClick={() => setPeriod(item.id)}
            >
              {item.label}
            </button>
          ))}
          {period === "month" && (
            <div className="flex items-center gap-1 ml-auto">
              <button
                type="button"
                className="fin-chip !px-2"
                aria-label="Mês anterior"
                onClick={() => setMonthCursor((d) => addMonths(d, -1))}
              >
                <SvgChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm font-medium min-w-[9.5rem] text-center">{bounds.label}</span>
              <button
                type="button"
                className="fin-chip !px-2"
                aria-label="Próximo mês"
                onClick={() => setMonthCursor((d) => addMonths(d, 1))}
              >
                <SvgChevronLeft className="w-4 h-4 rotate-180" />
              </button>
            </div>
          )}
        </div>
        {period === "custom" && (
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted block mb-1.5">De</label>
              <input
                type="date"
                className="input-glass"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-muted block mb-1.5">Até</label>
              <input
                type="date"
                className="input-glass"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
              />
            </div>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {(
            [
              ["all", "Tudo"],
              ["income", "Entradas"],
              ["expense", "Gastos"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`fin-chip ${id !== "all" ? id : ""} ${kind === id ? "active" : ""}`}
              onClick={() => setKind(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="grid sm:grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-muted block mb-1.5">Categoria</label>
            <select
              className="input-glass"
              value={category}
              disabled={kind === "all"}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">{kind === "all" ? "Escolha entradas ou gastos" : "Todas"}</option>
              {catOptions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted block mb-1.5">Forma de pagamento</label>
            <select
              className="input-glass"
              value={paymentMethod}
              onChange={(e) => setPaymentMethod(e.target.value)}
            >
              <option value="">Todas</option>
              {(meta?.payment_methods || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted block mb-1.5">Buscar</label>
            <input
              className="input-glass"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Título, detalhe, categoria…"
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="glass-card p-4">
          <p className="text-[11px] text-muted">Entradas</p>
          <p className="text-lg font-bold tabular-nums text-[var(--success)]">{formatPrice(totals.income)}</p>
        </div>
        <div className="glass-card p-4">
          <p className="text-[11px] text-muted">Gastos</p>
          <p className="text-lg font-bold tabular-nums text-[var(--danger)]">{formatPrice(totals.expense)}</p>
        </div>
        <div className="glass-card p-4">
          <p className="text-[11px] text-muted">Saldo</p>
          <p
            className={`text-lg font-bold tabular-nums ${
              totals.balance >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"
            }`}
          >
            {formatPrice(totals.balance)}
          </p>
        </div>
      </div>

      {error && (
        <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-3">{error}</p>
      )}

      <div className="glass-card overflow-hidden">
        {loading && rows.length === 0 ? (
          <p className="text-sm text-muted text-center py-12 px-4">Carregando lançamentos…</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-muted text-center py-12 px-4">
            Nenhum lançamento neste período. Use adicionar entrada ou adicionar gasto para começar.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--glass-border)]">
            {filtered.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className="w-full text-left px-4 sm:px-5 py-4 hover:bg-[var(--bg-elevated)] transition-colors flex items-center gap-4"
                  onClick={() => setEditing(row)}
                >
                  <span className={`fin-kind-dot ${row.kind}`} />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium truncate">
                      {transactionLabel(row.title, labelOf(meta, row.kind, row.category))}
                    </p>
                    <p className="text-xs text-muted mt-0.5">
                      {new Date(`${row.occurred_on}T12:00:00`).toLocaleDateString("pt-BR")}
                      {" · "}
                      {labelOf(meta, row.kind, row.category)}
                      {" · "}
                      {labelMethod(meta, row.payment_method)}
                      {row.has_receipt ? " · nota fiscal" : ""}
                    </p>
                    {row.notes && <p className="text-xs text-secondary mt-1 line-clamp-2">{row.notes}</p>}
                  </div>
                  <span
                    className={`font-semibold tabular-nums ${
                      row.kind === "income" ? "text-[var(--success)]" : "text-[var(--danger)]"
                    }`}
                  >
                    {signedPrice(row.amount_cents, row.kind)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing && (
        <TransactionModal
          seed={
            editing === "new-income" ? "income" : editing === "new-expense" ? "expense" : editing
          }
          meta={meta}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function labelOf(meta: FinanceMeta | null, kind: FinanceKind, id: string): string {
  const list = kind === "income" ? meta?.income_categories : meta?.expense_categories;
  return list?.find((item) => item.id === id)?.label || id;
}

function labelMethod(meta: FinanceMeta | null, id: string): string {
  return meta?.payment_methods.find((item) => item.id === id)?.label || id;
}

function TransactionModal({
  seed,
  meta,
  onClose,
  onSaved,
}: {
  seed: FinanceKind | FinanceTransaction;
  meta: FinanceMeta | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const existing = typeof seed === "object" ? seed : null;
  const initialKind: FinanceKind = typeof seed === "object" ? seed.kind : seed;
  const categories = useMemo(() => {
    if (!meta) return [];
    return initialKind === "income" ? meta.income_categories : meta.expense_categories;
  }, [meta, initialKind]);

  const initial = useMemo(
    () => ({
      kind: initialKind,
      title: existing?.title || "",
      amount: existing ? centsToInput(existing.amount_cents) : "",
      category: existing?.category || categories[0]?.id || "outro",
      payment_method: existing?.payment_method || "pix",
      notes: existing?.notes || "",
      occurred_on: existing?.occurred_on || todayISODate(),
    }),
    [existing, initialKind, categories]
  );

  const [form, setForm] = useState(initial);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [removeReceipt, setRemoveReceipt] = useState(false);

  useEffect(() => setForm(initial), [initial]);

  useEffect(() => {
    let url = "";
    if (receiptFile) {
      url = URL.createObjectURL(receiptFile);
      setPreview(url);
      return () => URL.revokeObjectURL(url);
    }
    if (existing?.has_receipt && !removeReceipt) {
      let cancelled = false;
      api
        .financeReceiptBlob(existing.id)
        .then((blob) => {
          if (cancelled) return;
          url = URL.createObjectURL(blob);
          setPreview(url);
        })
        .catch(() => setPreview(""));
      return () => {
        cancelled = true;
        if (url) URL.revokeObjectURL(url);
      };
    }
    setPreview("");
    return undefined;
  }, [existing, receiptFile, removeReceipt]);

  const catOptions =
    form.kind === "income" ? meta?.income_categories || [] : meta?.expense_categories || [];

  const payload = (): FinanceTransactionPayload | null => {
    const amount_cents = parseBRLToCents(form.amount);
    if (!amount_cents) return null;
    return {
      kind: form.kind,
      title: form.title.trim(),
      amount_cents,
      category: form.category,
      payment_method: form.payment_method,
      notes: form.notes.trim(),
      occurred_on: form.occurred_on,
    };
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const data = payload();
    if (!data) {
      setError("Informe um valor válido, por exemplo 150,90");
      return;
    }
    setLoading(true);
    setError("");
    try {
      let saved = existing
        ? await api.financeUpdateTransaction(existing.id, data)
        : await api.financeCreateTransaction(data);
      if (receiptFile) {
        saved = await api.financeUploadReceipt(saved.id, receiptFile);
      } else if (existing?.has_receipt && removeReceipt) {
        saved = await api.financeDeleteReceipt(existing.id);
      }
      void saved;
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setLoading(false);
    }
  };

  const remove = async () => {
    if (!existing) return;
    setLoading(true);
    setError("");
    try {
      await api.financeDeleteTransaction(existing.id);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir");
      setLoading(false);
    }
  };

  const heading = existing
    ? "Editar lançamento"
    : form.kind === "income"
      ? "Adicionar entrada"
      : "Adicionar gasto";

  return (
    <div className="fin-modal-backdrop" onClick={onClose} role="presentation">
      <form className="glass-card fin-modal" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h2 className="text-lg font-semibold mb-4">{heading}</h2>
        <div className="space-y-4">
          <div className="flex gap-2">
            {(["income", "expense"] as const).map((id) => (
              <button
                key={id}
                type="button"
                className={`fin-chip flex-1 justify-center ${id} ${form.kind === id ? "active" : ""}`}
                onClick={() =>
                  setForm({
                    ...form,
                    kind: id,
                    category:
                      (id === "income" ? meta?.income_categories[0]?.id : meta?.expense_categories[0]?.id) ||
                      "outro",
                  })
                }
              >
                {id === "income" ? "Entrada" : "Gasto"}
              </button>
            ))}
          </div>
          <div>
            <label className="text-xs text-muted block mb-1.5">Título (opcional)</label>
            <input
              className="input-glass"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder={form.kind === "income" ? "Salário, freelance…" : "Mercado, dentista, luz…"}
            />
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-muted block mb-1.5">Valor (R$)</label>
              <input
                required
                inputMode="decimal"
                className="input-glass"
                placeholder="0,00"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted block mb-1.5">Data</label>
              <input
                type="date"
                required
                className="input-glass"
                value={form.occurred_on}
                onChange={(e) => setForm({ ...form, occurred_on: e.target.value })}
              />
            </div>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-muted block mb-1.5">Categoria</label>
              <select
                className="input-glass"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              >
                {catOptions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted block mb-1.5">Forma de pagamento</label>
              <select
                className="input-glass"
                value={form.payment_method}
                onChange={(e) => setForm({ ...form, payment_method: e.target.value })}
              >
                {(meta?.payment_methods || []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs text-muted block mb-1.5">Detalhes</label>
            <textarea
              className="input-glass min-h-[88px] resize-y"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Observações, parcela, local…"
            />
          </div>
          <div>
            <label className="text-xs text-muted block mb-1.5">Nota fiscal (imagem)</label>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="input-glass py-2"
              onChange={(e) => {
                setReceiptFile(e.target.files?.[0] || null);
                setRemoveReceipt(false);
              }}
            />
            <p className="text-[11px] text-muted mt-1">JPG, PNG ou WEBP até 8 MB. Serve para entrada e gasto.</p>
            {preview && (
              <img src={preview} alt="Nota fiscal" className="mt-3 max-h-40 rounded-lg border border-[var(--glass-border)]" />
            )}
            {(preview || existing?.has_receipt) && (
              <button
                type="button"
                className="btn-ghost !py-1.5 !px-3 text-xs mt-2"
                onClick={() => {
                  setReceiptFile(null);
                  setRemoveReceipt(true);
                  setPreview("");
                }}
              >
                Remover nota
              </button>
            )}
          </div>
          {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
          {existing && (
            <p className="text-xs text-muted">Valor atual: {formatPrice(existing.amount_cents)}</p>
          )}
        </div>
        <div className="flex flex-wrap justify-between gap-2 mt-6">
          {existing ? (
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
