"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { SvgChevronLeft } from "@/components/ui/svgs";
import { VpsActions } from "@/components/VpsActions";
import { VpsRenewalPanel } from "@/components/VpsRenewalPanel";
import { VpsUpgradePanel } from "@/components/VpsUpgradePanel";
import { VpsCredentialsPanel } from "@/components/VpsCredentialsPanel";
import { VpsConnectionsPanel } from "@/components/VpsConnectionsPanel";
import { VpsMetricsPanel } from "@/components/VpsMetricsPanel";
import { VpsStatusBadge } from "@/components/VpsStatusBadge";
import { PowerStateBadge } from "@/components/PowerStateBadge";
import { api, getToken, type VpsInstanceDetail } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

type VpsTab = "overview" | "rdp" | "connections" | "billing" | "upgrade";

function parseVpsTab(value: string | null): VpsTab {
  if (value === "rdp" || value === "connections" || value === "ports" || value === "billing" || value === "upgrade") {
    return value === "ports" ? "connections" : value;
  }
  return "overview";
}

export default function VpsDetailPage() {
  return (
    <Suspense fallback={<PageLoader label="Carregando VPS…" />}>
      <VpsDetailPageContent />
    </Suspense>
  );
}

function VpsDetailPageContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const id = Number(params.id);
  const [instance, setInstance] = useState<VpsInstanceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<VpsTab>(() => parseVpsTab(searchParams.get("tab")));

  const load = async () => {
    try {
      const data = await api.instance(id);
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
    if (!Number.isFinite(id)) {
      router.push("/dashboard");
      return;
    }
    load();
  }, [id, router]);

  useEffect(() => {
    const interval = setInterval(load, instance?.is_provisioning ? 2000 : 5000);
    return () => clearInterval(interval);
  }, [id, instance?.is_provisioning]);

  useEffect(() => {
    setActiveTab(parseVpsTab(searchParams.get("tab")));
  }, [searchParams]);

  const tabBtn = (id: VpsTab, label: string) => (
    <button
      type="button"
      onClick={() => setActiveTab(id)}
      className={`px-4 py-2 rounded-xl text-sm font-medium transition ${
        activeTab === id ? "btn-primary !py-2" : "btn-ghost !py-2"
      }`}
    >
      {label}
    </button>
  );

  if (loading) {
    return <PageLoader label="Carregando VPS…" />;
  }

  if (!instance || error) {
    return (
      <>
        <p className="text-[var(--danger)]">{error || "VPS não encontrada"}</p>
        <Link href="/dashboard" className="text-[var(--accent)] hover:underline text-sm mt-4 inline-block">
          ← Voltar aos servidores
        </Link>
      </>
    );
  }

  const isOn = instance.power_state === "poweredOn";
  const isProvisioning = instance.is_provisioning;
  const billing = instance.billing;
  const billingNeedsAttention =
    billing &&
    (billing.billing_state === "grace" || billing.billing_state === "suspended");

  return (
    <>
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-[var(--accent)] mb-8 transition-colors"
      >
        <SvgChevronLeft className="w-4 h-4" />
        Meus servidores
      </Link>

      <div className="glass-card p-6 sm:p-8 mb-6">
        <div className="flex flex-wrap gap-6 justify-between items-start">
          <div className="flex items-start gap-4">
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 ${
                isOn
                  ? "bg-gradient-to-br from-emerald-500/20 to-brand-500/20 shadow-lg shadow-emerald-500/10"
                  : "bg-[var(--glass-bg)]"
              }`}
            >
              <div className={`status-dot ${isOn ? "status-dot-on" : "status-dot-off"} !w-4 !h-4`} />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{instance.vm_name}</h1>
              <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-secondary">
                <span>{instance.vcpu} vCPU</span>
                <span className="text-muted">·</span>
                <span>{instance.ram_mb / 1024} GB RAM</span>
                <span className="text-muted">·</span>
                <span>{instance.disk_gb ?? 30} GB disco</span>
                {instance.network_mbps && (
                  <>
                    <span className="text-muted">·</span>
                    <span>{instance.network_mbps} Mb/s</span>
                  </>
                )}
                {instance.os_label && (
                  <>
                    <span className="text-muted">·</span>
                    <span>{instance.os_label}</span>
                  </>
                )}
                {instance.plan_name && (
                  <>
                    <span className="text-muted">·</span>
                    <span>{instance.plan_name}</span>
                  </>
                )}
                {instance.billing?.paid_until && (
                  <>
                    <span className="text-muted">·</span>
                    <span className="text-[var(--accent)]">
                      Vence{" "}
                      {new Date(instance.billing.paid_until).toLocaleDateString("pt-BR")}
                    </span>
                  </>
                )}
              </div>
              {instance.os_label && (
                <p className="text-xs text-muted mt-2">{instance.os_label}</p>
              )}
              {instance.error_message && (
                <p className="text-xs text-[var(--danger)] mt-2">{instance.error_message}</p>
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <PowerStateBadge powerState={instance.power_state} />
            <VpsStatusBadge status={instance.status} />
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        {tabBtn("overview", "Uso, controle & zona")}
        {tabBtn("rdp", "Acesso RDP")}
        {tabBtn("connections", "Conexões")}
        {tabBtn("billing", "Plano & pagamento")}
        {tabBtn("upgrade", "Upgrade")}
      </div>

      {activeTab === "overview" && (
        <>
          {billingNeedsAttention && (
            <div className="rounded-xl border border-[var(--warning)]/30 bg-[var(--warning)]/10 px-4 py-3 mb-6 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-[var(--warning)]">
                {billing!.billing_state === "grace"
                  ? `Mensalidade vencida. Carência de ${billing!.days_in_grace_left} dia(s).`
                  : "Servidor suspenso por inadimplência. Renove para ligar novamente."}
              </p>
              <button
                type="button"
                onClick={() => setActiveTab("billing")}
                className="btn-primary text-sm !py-2 shrink-0"
              >
                Ver plano & pagamento
              </button>
            </div>
          )}

          <div className="grid lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3">
              {isProvisioning ? (
                <div className="glass-card p-8 text-center text-secondary text-sm">
                  <p>Métricas de CPU, RAM e disco ficarão disponíveis quando o servidor estiver pronto.</p>
                </div>
              ) : (
                <VpsMetricsPanel metrics={instance.metrics} powerState={instance.power_state} />
              )}
            </div>
            <div className="lg:col-span-2">
              <VpsActions
                instance={instance}
                actions={{
                  powerOn: api.instancePowerOn,
                  powerOff: api.instancePowerOff,
                  reset: api.instanceReset,
                  destroy: api.instanceDestroy,
                }}
                onUpdated={load}
                backHref="/dashboard"
                onOpenBilling={() => setActiveTab("billing")}
              />
            </div>
          </div>
        </>
      )}

      {activeTab === "rdp" && (
        isProvisioning ? (
          <div className="glass-card p-8 text-center text-secondary text-sm max-w-lg mx-auto">
            <p>Credenciais RDP ficarão disponíveis quando o servidor terminar de ser criado.</p>
          </div>
        ) : !instance.windows_credentials ? (
          <div className="glass-card p-8 text-center text-secondary text-sm max-w-lg mx-auto">
            <p>Esta VPS não possui acesso RDP Windows configurado.</p>
          </div>
        ) : (
          <div className="space-y-4">
            <VpsCredentialsPanel
              instanceId={instance.id}
              rdpConnectionAddress={instance.rdp_connection_address}
              osLabel={instance.os_label}
              vmName={instance.vm_name}
              username={instance.windows_credentials.username}
              password={instance.windows_credentials.password}
              hasPassword={instance.windows_credentials.has_password}
            />
          </div>
        )
      )}

      {activeTab === "connections" && (
        isProvisioning ? (
          <div className="glass-card p-8 text-center text-secondary text-sm max-w-lg mx-auto">
            <p>Conexões ficarão disponíveis quando o servidor terminar de ser criado.</p>
          </div>
        ) : (
          <VpsConnectionsPanel
            instanceId={instance.id}
            mappings={instance.port_mappings ?? []}
            connections={instance.connection_domains ?? []}
            dnsTarget={instance.dns_target ?? ""}
            publicHost={instance.port_mappings?.[0]?.public_host}
            onUpdated={load}
          />
        )
      )}

      {activeTab === "billing" && (
        isProvisioning ? (
          <div className="glass-card p-8 text-center text-secondary text-sm">
            <p>Plano e pagamento ficam disponíveis quando o servidor terminar de ser criado.</p>
          </div>
        ) : (
          <VpsRenewalPanel instance={instance} onUpdated={load} embedded />
        )
      )}

      {activeTab === "upgrade" && (
        isProvisioning ? (
          <div className="glass-card p-8 text-center text-secondary text-sm">
            <p>Upgrade ficará disponível quando o servidor estiver pronto.</p>
          </div>
        ) : instance.billing?.billing_state === "suspended" ? (
          <div className="glass-card p-8 text-center text-secondary text-sm space-y-4">
            <p>Servidor suspenso por inadimplência. Renove na aba Plano & pagamento antes de fazer upgrade.</p>
            <button type="button" onClick={() => setActiveTab("billing")} className="btn-primary text-sm !py-2">
              Ir para plano & pagamento
            </button>
          </div>
        ) : (
          <VpsUpgradePanel instance={instance} onUpdated={load} embedded />
        )
      )}
    </>
  );
}
