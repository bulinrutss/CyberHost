"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { PageShell } from "@/components/ui/PageShell";
import { WebSitePanel } from "@/components/WebSitePanel";
import { api, formatPrice, getToken, type WebSiteAdminDetail } from "@/lib/api";
import { formatPhoneDisplay } from "@/lib/phone";
import { PageLoader } from "@/components/PageLoader";

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    running: "Online",
    stopped: "Parado",
    starting: "Iniciando",
    stopping: "Parando",
    creating: "Criando",
    error: "Erro",
  };
  return map[status] ?? status;
}

export default function AdminWebSiteDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const [site, setSite] = useState<WebSiteAdminDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);

  const load = async () => {
    try {
      const data = await api.adminWebSite(id);
      setSite(data);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Site não encontrado");
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
      router.push("/admin?tab=sites");
      return;
    }
    load();
    const interval = setInterval(load, 8000);
    return () => clearInterval(interval);
  }, [id, router]);

  const deleteSite = async () => {
    if (!site) return;
    const label = site.domain || site.site_slug;
    if (
      !window.confirm(
        `Apagar o site "${label}"? O processo será parado, os arquivos removidos e o nginx atualizado.`
      )
    ) {
      return;
    }
    setDeleting(true);
    try {
      await api.adminDeleteWebSite(site.id);
      router.push("/admin?tab=sites");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível apagar o site");
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <PageShell admin>
        <PageLoader label="Carregando site…" />
      </PageShell>
    );
  }

  if (!site || error) {
    return (
      <PageShell admin>
        <p className="text-[var(--danger)]">{error || "Site não encontrado"}</p>
        <Link href="/admin?tab=sites" className="text-[var(--accent)] text-sm mt-4 inline-block">
          ← Todos os sites
        </Link>
      </PageShell>
    );
  }

  const isRunning = site.status === "running";

  return (
    <PageShell admin wide>
      <Link href="/admin?tab=sites" className="text-sm text-muted hover:text-[var(--accent)] mb-8 inline-block">
        ← Todos os sites
      </Link>

      <div className="glass-card p-6 sm:p-8 mb-6">
        <div className="flex flex-wrap gap-6 justify-between items-start">
          <div className="flex items-start gap-4 min-w-0">
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 ${
                isRunning ? "bg-gradient-to-br from-emerald-500/20 to-brand-500/20" : "bg-[var(--glass-bg)]"
              }`}
            >
              <div className={`status-dot ${isRunning ? "status-dot-on" : "status-dot-off"} !w-4 !h-4`} />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-[var(--accent)] uppercase tracking-wide">
                {site.php_enabled ? "PHP" : "Estático"}
              </p>
              <h1 className="text-2xl sm:text-3xl font-bold truncate">{site.domain || site.site_slug}</h1>
              <p className="text-secondary text-sm mt-1">
                Cliente: {site.user_name} ({formatPhoneDisplay(site.user_phone)})
              </p>
              <p className="text-muted text-sm font-mono truncate mt-1">{site.public_url}</p>
              <div className="flex flex-wrap gap-3 mt-2 text-sm text-secondary">
                <span>{site.ram_mb} MB RAM</span>
                <span>·</span>
                <span>{site.disk_mb} MB disco</span>
                <span>·</span>
                <span>porta {site.port}</span>
                {site.ssl_active ? (
                  <>
                    <span>·</span>
                    <span className="text-emerald-400">HTTPS</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-[var(--glass-bg)] border border-[var(--glass-border)]">
              {statusLabel(site.status)}
            </span>
            <Link href="/admin?tab=accounts" className="btn-ghost text-xs !py-1.5 !px-3">
              Ver conta
            </Link>
            <button
              type="button"
              disabled={deleting}
              onClick={() => void deleteSite()}
              className="btn-ghost text-xs !py-1.5 !px-3 !text-[var(--danger)] !border-[var(--danger)]/30 hover:!bg-[var(--danger)]/10"
            >
              {deleting ? "Apagando…" : "Apagar site"}
            </button>
          </div>
        </div>

        {site.billing?.paid_until ? (
          <p className="text-xs text-muted mt-4">
            Vence {new Date(site.billing.paid_until).toLocaleDateString("pt-BR")}
            {" · "}
            {formatPrice(site.billing.monthly_cents)}/mês
            {site.billing.suspended_for_billing ? " · suspenso por billing" : ""}
          </p>
        ) : null}

        {site.error_message ? (
          <p className="text-sm text-red-400 mt-4 break-words">{site.error_message}</p>
        ) : null}
      </div>

      <WebSitePanel site={site} onRefresh={load} admin />
    </PageShell>
  );
}
