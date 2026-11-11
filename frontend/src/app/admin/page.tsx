"use client";

import { useEffect, useMemo, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { PageShell } from "@/components/ui/PageShell";
import { VpsStatusBadge } from "@/components/VpsStatusBadge";
import { AdminAccountsPanel } from "@/components/AdminAccountsPanel";
import { AdminCouponsPanel } from "@/components/AdminCouponsPanel";
import { AdminImportPanel } from "@/components/AdminImportPanel";
import { AdminInfraPanel, type InfraSection } from "@/components/AdminInfraPanel";
import { AdminSupportPanel } from "@/components/AdminSupportPanel";
import { AdminNginxProxyPanel } from "@/components/AdminNginxProxyPanel";
import { AdminStatsPanel } from "@/components/AdminStatsPanel";
import { api, getToken, type User, type VpsInstanceAdmin, type WebSiteAdmin } from "@/lib/api";
import { formatPhoneDisplay } from "@/lib/phone";
import { matchesAdminQuery } from "@/lib/adminSearch";
import { AdminSearchInput } from "@/components/AdminSearchInput";
import { PageLoader } from "@/components/PageLoader";

type Tab = "stats" | "infra" | "support" | "accounts" | "vps" | "sites" | "import" | "coupons" | "proxy";

const TABS: Tab[] = ["stats", "infra", "support", "accounts", "vps", "sites", "import", "coupons", "proxy"];

function isTab(value: string | null): value is Tab {
  return !!value && TABS.includes(value as Tab);
}

function tabFromQuery(value: string | null): Tab {
  if (value === "users") return "accounts";
  if (value === "machine" || value === "server" || value === "esxi") return "infra";
  return isTab(value) ? value : "stats";
}

function infraSectionFromQuery(value: string | null): InfraSection {
  if (value === "esxi") return "esxi";
  if (value === "server") return "files";
  return "machine";
}

function AdminPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<Tab>(() => tabFromQuery(searchParams.get("tab")));
  const [users, setUsers] = useState<User[]>([]);
  const [instances, setInstances] = useState<VpsInstanceAdmin[]>([]);
  const [sites, setSites] = useState<WebSiteAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [vpsQuery, setVpsQuery] = useState("");
  const [sitesQuery, setSitesQuery] = useState("");

  const emailByUser = useMemo(() => new Map(users.map((user) => [user.id, user.email])), [users]);

  const filteredInstances = useMemo(() => {
    return instances.filter((vps) =>
      matchesAdminQuery(vpsQuery, [
        vps.vm_name,
        vps.user_name,
        vps.user_phone,
        formatPhoneDisplay(vps.user_phone),
        emailByUser.get(vps.user_id),
      ])
    );
  }, [instances, emailByUser, vpsQuery]);

  const filteredSites = useMemo(() => {
    return sites.filter((site) =>
      matchesAdminQuery(sitesQuery, [
        site.site_slug,
        site.domain,
        site.public_url,
        site.user_name,
        site.user_phone,
        formatPhoneDisplay(site.user_phone),
        emailByUser.get(site.user_id),
      ])
    );
  }, [sites, emailByUser, sitesQuery]);

  useEffect(() => {
    setTab(tabFromQuery(searchParams.get("tab")));
  }, [searchParams]);

  const selectTab = (id: Tab) => {
    setTab(id);
    const url = new URL(window.location.href);
    if (id === "stats") url.searchParams.delete("tab");
    else url.searchParams.set("tab", id);
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  };

  const load = async () => {
    try {
      const [u, inst, webSites] = await Promise.all([
        api.adminUsers(),
        api.adminInstances(),
        api.adminWebSites(),
      ]);
      setUsers(u);
      setInstances(inst.filter((v) => v.status !== "deleted"));
      setSites(webSites.filter((s) => s.status !== "deleted"));
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
        else load();
      })
      .catch(() => router.push("/login"));
  }, [router]);

  const tabBtn = (id: Tab, label: string) => (
    <button
      type="button"
      onClick={() => selectTab(id)}
      className={`px-4 py-2 rounded-xl text-sm font-medium transition ${
        tab === id ? "btn-primary !py-2" : "btn-ghost !py-2"
      }`}
    >
      {label}
    </button>
  );

  return (
    <PageShell admin wide>
        <p className="text-sm text-[var(--accent)] uppercase tracking-wide mb-2">Administração</p>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">Painel administrativo</h1>
        <p className="text-secondary mb-8">
          Gerencie clientes, VPS e acompanhe pedidos, erros e uso do servidor
          {" · "}
          <Link href="/pixdev" className="text-[var(--accent)] hover:underline">
            Pix DevMode
          </Link>
        </p>

        {message && (
          <p className="text-green-400 text-sm bg-green-400/10 border border-green-800 rounded-xl px-4 py-3 mb-4">
            {message}
          </p>
        )}
        {error && (
          <p className="text-red-400 text-sm bg-red-400/10 border border-red-800 rounded-xl px-4 py-3 mb-4">
            {error}
          </p>
        )}

        <div className="flex flex-wrap gap-2 mb-8">
          {tabBtn("stats", "Estatísticas")}
          {tabBtn("infra", "Infra")}
          {tabBtn("support", "Suporte")}
          {tabBtn("accounts", "Contas & Cloud")}
          {tabBtn("vps", "Todas as VPS")}
          {tabBtn("sites", "Todos os sites")}
          {tabBtn("import", "Importar VMs")}
          {tabBtn("coupons", "Cupons")}
          {tabBtn("proxy", "Proxy nginx")}
        </div>

        {tab === "support" ? (
          <AdminSupportPanel />
        ) : tab === "infra" ? (
          <AdminInfraPanel initialSection={infraSectionFromQuery(searchParams.get("tab"))} />
        ) : tab === "import" ? (
          <AdminImportPanel />
        ) : tab === "proxy" ? (
          <AdminNginxProxyPanel />
        ) : loading ? (
          <PageLoader label="Carregando painel…" compact />
        ) : tab === "stats" ? (
          <AdminStatsPanel />
        ) : tab === "accounts" ? (
          <AdminAccountsPanel
            users={users}
            instances={instances}
            onRefresh={load}
            onMessage={setMessage}
            onError={setError}
          />
        ) : tab === "vps" ? (
          <div className="space-y-4">
            <div className="glass-card p-4">
              <p className="text-sm font-medium mb-3">
                Todas as VPS (
                {vpsQuery.trim() ? `${filteredInstances.length} de ${instances.length}` : instances.length})
              </p>
              <AdminSearchInput value={vpsQuery} onChange={setVpsQuery} />
            </div>
            {instances.length === 0 ? (
              <p className="text-muted">Nenhuma VPS cadastrada</p>
            ) : filteredInstances.length === 0 ? (
              <p className="text-muted">Nenhuma VPS encontrada.</p>
            ) : (
              filteredInstances.map((vps) => (
                <Link
                  key={vps.id}
                  href={`/admin/vps/${vps.id}`}
                  className="block glass-card p-6 hover:border-[var(--accent)] transition"
                >
                  <div className="flex flex-wrap gap-4 justify-between items-center">
                    <div>
                      <h3 className="font-bold">{vps.vm_name}</h3>
                      <p className="text-secondary text-sm">
                        Cliente: {vps.user_name} ({formatPhoneDisplay(vps.user_phone)})
                      </p>
                      {emailByUser.get(vps.user_id) ? (
                        <p className="text-muted text-sm truncate">{emailByUser.get(vps.user_id)}</p>
                      ) : null}
                      <p className="text-muted text-sm">
                        {vps.vcpu} vCPU · {vps.ram_mb / 1024} GB RAM
                        {vps.ip_address && (
                          <> · IP: <span className="font-mono text-brand-500">{vps.ip_address}</span></>
                        )}
                      </p>
                    </div>
                    <VpsStatusBadge status={vps.status} />
                  </div>
                </Link>
              ))
            )}
          </div>
        ) : tab === "sites" ? (
          <div className="space-y-4">
            <div className="glass-card p-4">
              <p className="text-sm font-medium mb-3">
                Todos os sites (
                {sitesQuery.trim() ? `${filteredSites.length} de ${sites.length}` : sites.length})
              </p>
              <AdminSearchInput value={sitesQuery} onChange={setSitesQuery} />
            </div>
            {sites.length === 0 ? (
              <p className="text-muted">Nenhum site cadastrado</p>
            ) : filteredSites.length === 0 ? (
              <p className="text-muted">Nenhum site encontrado.</p>
            ) : (
              filteredSites.map((site) => (
                <Link
                  key={site.id}
                  href={`/admin/sites/${site.id}`}
                  className="block glass-card p-6 hover:border-[var(--accent)] transition"
                >
                  <div className="flex flex-wrap gap-4 justify-between items-center">
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-[var(--accent)] uppercase tracking-wide">
                        {site.php_enabled ? "PHP" : "Estático"}
                      </p>
                      <h3 className="font-bold truncate">{site.domain || site.site_slug}</h3>
                      <p className="text-secondary text-sm">
                        Cliente: {site.user_name} ({formatPhoneDisplay(site.user_phone)})
                      </p>
                      {emailByUser.get(site.user_id) ? (
                        <p className="text-muted text-sm truncate">{emailByUser.get(site.user_id)}</p>
                      ) : null}
                      <p className="text-muted text-sm font-mono truncate">{site.public_url}</p>
                      <p className="text-muted text-sm">
                        {site.ram_mb} MB RAM · {site.disk_mb} MB disco · porta {site.port}
                        {site.ssl_active ? " · HTTPS" : ""}
                      </p>
                    </div>
                    <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-[var(--glass-bg)] border border-[var(--glass-border)] shrink-0">
                      {site.status === "running"
                        ? "Online"
                        : site.status === "stopped"
                          ? "Parado"
                          : site.status.replaceAll("_", " ")}
                    </span>
                  </div>
                </Link>
              ))
            )}
          </div>
        ) : (
          <AdminCouponsPanel />
        )}
    </PageShell>
  );
}

export default function AdminPage() {
  return (
    <Suspense fallback={<PageLoader label="Carregando painel…" />}>
      <AdminPageInner />
    </Suspense>
  );
}
