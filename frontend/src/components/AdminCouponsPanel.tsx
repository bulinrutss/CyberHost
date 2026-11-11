"use client";

import { useEffect, useState } from "react";
import { api, formatPrice, type DiscountCoupon } from "@/lib/api";
import { InlineLoader } from "@/components/PageLoader";

export function AdminCouponsPanel() {
  const [coupons, setCoupons] = useState<DiscountCoupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({
    code: "",
    description: "",
    discountType: "percent" as "percent" | "fixed",
    discountPercent: "10",
    discountCents: "1000",
    maxUses: "",
    validUntil: "",
  });

  const load = async () => {
    setLoading(true);
    try {
      setCoupons(await api.adminCoupons());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar cupons");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await api.adminCreateCoupon({
        code: form.code,
        description: form.description,
        discount_percent:
          form.discountType === "percent" ? Number(form.discountPercent) : undefined,
        discount_cents: form.discountType === "fixed" ? Number(form.discountCents) : undefined,
        max_uses: form.maxUses ? Number(form.maxUses) : undefined,
        valid_until: form.validUntil ? new Date(form.validUntil).toISOString() : undefined,
      });
      setMessage("Cupom criado");
      setForm({
        code: "",
        description: "",
        discountType: "percent",
        discountPercent: "10",
        discountCents: "1000",
        maxUses: "",
        validUntil: "",
      });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar cupom");
    }
  };

  const toggleActive = async (coupon: DiscountCoupon) => {
    setError("");
    try {
      await api.adminUpdateCoupon(coupon.id, { is_active: !coupon.is_active });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao atualizar cupom");
    }
  };

  const formatDiscount = (c: DiscountCoupon) =>
    c.discount_percent ? `${c.discount_percent}%` : formatPrice(c.discount_cents ?? 0);

  return (
    <div className="space-y-8">
      <form onSubmit={create} className="glass-card p-6 space-y-4 max-w-xl">
        <h2 className="text-lg font-semibold">Novo cupom de desconto</h2>
        <div>
          <label className="text-sm block mb-1">Código</label>
          <input
            required
            className="input-glass"
            placeholder="LANCAMENTO10"
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
          />
        </div>
        <div>
          <label className="text-sm block mb-1">Descrição (opcional)</label>
          <input
            className="input-glass"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className={form.discountType === "percent" ? "btn-primary !py-2" : "btn-ghost !py-2"}
            onClick={() => setForm({ ...form, discountType: "percent" })}
          >
            Percentual
          </button>
          <button
            type="button"
            className={form.discountType === "fixed" ? "btn-primary !py-2" : "btn-ghost !py-2"}
            onClick={() => setForm({ ...form, discountType: "fixed" })}
          >
            Valor fixo
          </button>
        </div>
        {form.discountType === "percent" ? (
          <div>
            <label className="text-sm block mb-1">Desconto (%)</label>
            <input
              type="number"
              min={1}
              max={100}
              required
              className="input-glass"
              value={form.discountPercent}
              onChange={(e) => setForm({ ...form, discountPercent: e.target.value })}
            />
          </div>
        ) : (
          <div>
            <label className="text-sm block mb-1">Desconto (centavos)</label>
            <input
              type="number"
              min={1}
              required
              className="input-glass"
              value={form.discountCents}
              onChange={(e) => setForm({ ...form, discountCents: e.target.value })}
            />
            <p className="text-xs text-muted mt-1">Ex.: 1000 = {formatPrice(1000)}</p>
          </div>
        )}
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="text-sm block mb-1">Limite de usos (opcional)</label>
            <input
              type="number"
              min={1}
              className="input-glass"
              value={form.maxUses}
              onChange={(e) => setForm({ ...form, maxUses: e.target.value })}
            />
          </div>
          <div>
            <label className="text-sm block mb-1">Válido até (opcional)</label>
            <input
              type="date"
              className="input-glass"
              value={form.validUntil}
              onChange={(e) => setForm({ ...form, validUntil: e.target.value })}
            />
          </div>
        </div>
        <button type="submit" className="btn-primary">
          Criar cupom
        </button>
      </form>

      {loading ? (
        <InlineLoader label="Carregando cupons…" />
      ) : coupons.length === 0 ? (
        <p className="text-secondary">Nenhum cupom cadastrado</p>
      ) : (
        <div className="glass-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--glass-border)] text-left text-muted">
                <th className="p-4">Código</th>
                <th className="p-4">Desconto</th>
                <th className="p-4">Usos</th>
                <th className="p-4">Validade</th>
                <th className="p-4">Status</th>
                <th className="p-4" />
              </tr>
            </thead>
            <tbody>
              {coupons.map((c) => (
                <tr key={c.id} className="border-b border-[var(--glass-border)]/50">
                  <td className="p-4 font-mono font-semibold">{c.code}</td>
                  <td className="p-4">{formatDiscount(c)}</td>
                  <td className="p-4">
                    {c.used_count}
                    {c.max_uses != null ? ` / ${c.max_uses}` : ""}
                  </td>
                  <td className="p-4 text-secondary">
                    {c.valid_until ? new Date(c.valid_until).toLocaleDateString("pt-BR") : "—"}
                  </td>
                  <td className="p-4">
                    <span
                      className={
                        c.is_active ? "text-[var(--success)]" : "text-[var(--danger)]"
                      }
                    >
                      {c.is_active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td className="p-4 text-right">
                    <button
                      type="button"
                      className="btn-ghost !py-1.5 !px-3 text-xs"
                      onClick={() => toggleActive(c)}
                    >
                      {c.is_active ? "Desativar" : "Ativar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {message && <p className="text-sm text-[var(--success)]">{message}</p>}
      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
    </div>
  );
}
