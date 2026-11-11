"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { PageShell } from "@/components/ui/PageShell";
import { VpsActions } from "@/components/VpsActions";
import { VpsCredentialsPanel } from "@/components/VpsCredentialsPanel";
import { VpsMetricsPanel } from "@/components/VpsMetricsPanel";
import { VpsStatusBadge } from "@/components/VpsStatusBadge";
import { PowerStateBadge } from "@/components/PowerStateBadge";
import { api, formatPrice, getToken, type VpsInstanceAdminDetail } from "@/lib/api";
import { formatPhoneDisplay } from "@/lib/phone";
import { PageLoader } from "@/components/PageLoader";

function RenewalCostEditor({
  instance,
  onSaved,
}: {
  instance: VpsInstanceAdminDetail;
  onSaved: () => void;
}) {
  const hasCustom = instance.custom_monthly_cents !== null && instance.custom_monthly_cents !== undefined;
  const planMonthly = instance.billing?.monthly_cents ?? null;

  const [inputCents, setInputCents] = useState<string>(
    hasCustom ? String((instance.custom_monthly_cents! / 100).toFixed(2)) : ""
  );
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function handleSave() {
    const raw = inputCents.replace(",", ".");
    const value = parseFloat(raw);
    if (isNaN(value) || value < 0) {
      setErr("Valor inválido.");
      return;
    }
    const cents = Math.round(value * 100);
    setSaving(true);
    setErr("");
    setMsg("");
    try {
      await api.adminUpdateVpsBilling(instance.id, { custom_monthly_cents: cents });
      setMsg("Valor de renovação atualizado.");
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erro ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    setSaving(true);
    setErr("");
    setMsg("");
    try {
      await api.adminUpdateVpsBilling(instance.id, { clear_custom_monthly_cents: true });
      setInputCents("");
      setMsg("Valor personalizado removido. Voltando ao preço do plano.");
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erro ao remover.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="glass-card p-6 mt-6">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-secondary mb-4">
        Custo de renovação
      </h3>

      <div className="space-y-3 text-sm mb-5">
        <div className="flex justify-between">
          <span className="text-secondary">Preço do plano</span>
          <span className="font-mono">
            {planMonthly !== null ? formatPrice(planMonthly) + "/mês" : "—"}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-secondary">Valor personalizado</span>
          <span className={`font-mono font-semibold ${hasCustom ? "text-[var(--accent)]" : "text-secondary"}`}>
            {hasCustom ? formatPrice(instance.custom_monthly_cents!) + "/mês" : "Não definido"}
          </span>
        </div>
        <div className="flex justify-between border-t border-[var(--glass-border)] pt-3">
          <span className="text-secondary">Valor cobrado na renovação</span>
          <span className="font-mono font-bold">
            {hasCustom
              ? formatPrice(instance.custom_monthly_cents!) + "/mês"
              : planMonthly !== null
              ? formatPrice(planMonthly) + "/mês"
              : "—"}
          </span>
        </div>
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary text-sm">R$</span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={inputCents}
            onChange={(e) => setInputCents(e.target.value)}
            placeholder="0.00"
            className="input-field pl-9 w-full"
          />
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary px-4 text-sm"
        >
          {saving ? "…" : "Salvar"}
        </button>
        {hasCustom && (
          <button
            onClick={handleClear}
            disabled={saving}
            className="btn-secondary px-4 text-sm text-[var(--danger)] border-[var(--danger)]/30 hover:bg-[var(--danger)]/10"
          >
            Remover
          </button>
        )}
      </div>

      <p className="text-xs text-secondary mt-2">
        Defina um valor fixo mensal para esta VPS. Deixe em branco e clique em Salvar para usar o
        preço calculado automaticamente pelo plano.
      </p>

      {msg && <p className="text-[var(--success)] text-xs mt-3">{msg}</p>}
      {err && <p className="text-[var(--danger)] text-xs mt-3">{err}</p>}
    </div>
  );
}

export default function AdminVpsDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const [instance, setInstance] = useState<VpsInstanceAdminDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const data = await api.adminInstance(id);
      setInstance(data);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "VPS não encontrada");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.me()
      .then((user) => {
        if (!user.is_admin) router.replace("/dashboard");
      })
      .catch(() => router.push("/login"));

    if (!Number.isFinite(id)) {
      router.push("/admin");
      return;
    }
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [id, router]);

  if (loading) {
    return (
      <PageShell admin>
        <PageLoader label="Carregando VPS…" />
      </PageShell>
    );
  }

  if (!instance || error) {
    return (
      <PageShell admin>
        <p className="text-[var(--danger)]">{error || "VPS não encontrada"}</p>
        <Link href="/admin" className="text-[var(--accent)] text-sm mt-4 inline-block">
          ← Painel admin
        </Link>
      </PageShell>
    );
  }

  const isOn = instance.power_state === "poweredOn";

  return (
    <PageShell admin wide>
      <Link href="/admin" className="text-sm text-muted hover:text-[var(--accent)] mb-8 inline-block">
        ← Administração
      </Link>

      <div className="glass-card p-6 sm:p-8 mb-6">
        <div className="flex flex-wrap gap-6 justify-between items-start">
          <div className="flex items-start gap-4">
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 ${
                isOn ? "bg-gradient-to-br from-emerald-500/20 to-brand-500/20" : "bg-[var(--glass-bg)]"
              }`}
            >
              <div className={`status-dot ${isOn ? "status-dot-on" : "status-dot-off"} !w-4 !h-4`} />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold">{instance.vm_name}</h1>
              <p className="text-secondary text-sm mt-1">
                {instance.user_name} · {formatPhoneDisplay(instance.user_phone)}
              </p>
              <div className="flex flex-wrap gap-3 mt-2 text-sm text-secondary">
                <span>{instance.vcpu} vCPU</span>
                <span>·</span>
                <span>{instance.ram_mb / 1024} GB RAM</span>
                {instance.ip_address && (
                  <>
                    <span>·</span>
                    <span className="font-mono text-[var(--accent)]">{instance.ip_address}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <PowerStateBadge powerState={instance.power_state} />
            <VpsStatusBadge status={instance.status} />
          </div>
        </div>
      </div>

      {instance.windows_credentials ? (
        <div className="mb-6">
          <VpsCredentialsPanel
            instanceId={instance.id}
            rdpConnectionAddress={instance.rdp_connection_address}
            osLabel={instance.os_label}
            vmName={instance.vm_name}
            username={instance.windows_credentials.username}
            password={instance.windows_credentials.password}
            hasPassword={instance.windows_credentials.has_password}
            admin
          />
        </div>
      ) : instance.status !== "creating" && instance.status !== "configuring" ? (
        <p className="text-sm text-muted mb-6">
          Credenciais RDP ainda não estão disponíveis para esta VPS.
        </p>
      ) : null}

      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3">
          <VpsMetricsPanel metrics={instance.metrics} powerState={instance.power_state} />
          <RenewalCostEditor instance={instance} onSaved={load} />
        </div>
        <div className="lg:col-span-2">
          <VpsActions
            instance={instance}
            allowChangeIp
            allowChangePassword
            hideCredentials
            actions={{
              powerOn: api.adminInstancePowerOn,
              powerOff: api.adminInstancePowerOff,
              reset: api.adminInstanceReset,
              changeIp: api.adminInstanceChangeIp,
              changePassword: api.adminInstanceChangePassword,
              destroy: api.adminInstanceDestroy,
            }}
            onUpdated={load}
            backHref="/admin"
          />
        </div>
      </div>
    </PageShell>
  );
}
