"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { WebSitePanel } from "@/components/WebSitePanel";
import { ProvisionProgress } from "@/components/ProvisionProgress";
import { api, type WebSite } from "@/lib/api";

export default function WebSiteDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const id = Number(params.id);
  const initialTab =
    searchParams.get("tab") === "billing" && !Number.isNaN(id) ? ("billing" as const) : undefined;
  const [site, setSite] = useState<WebSite | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const s = await api.webSite(id);
      setSite(s);
    } catch {
      router.push("/dashboard/sites");
    } finally {
      setLoading(false);
    }
  }, [id, router]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!site?.is_provisioning) return;
    const interval = setInterval(() => void load(), 2000);
    return () => clearInterval(interval);
  }, [site?.is_provisioning, load]);

  if (loading || !site) {
    return <div className="glass-card p-12 shimmer h-64 rounded-2xl" />;
  }

  return (
    <>
      <div className="mb-8">
        <Link href="/dashboard/sites" className="text-sm text-[var(--accent)] hover:underline">
          ← Meus sites
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mt-4">
          <div>
            <p className="text-sm font-medium text-[var(--accent)]">
              {site.php_enabled ? "PHP" : "Site estático"}
            </p>
            <h1 className="text-3xl font-bold">{site.domain || site.site_slug}</h1>
            <p className="font-mono text-secondary mt-1">{site.public_url}</p>
          </div>
        </div>
      </div>

      {site.is_provisioning ? (
        <div className="glass-card p-8 text-center">
          <ProvisionProgress
            progress={site.provision_progress ?? 0}
            label={site.provision_label || "Publicando site..."}
          />
          <p className="text-sm text-muted mt-4">Aguarde alguns instantes...</p>
        </div>
      ) : (
        <WebSitePanel site={site} onRefresh={() => void load()} initialTab={initialTab} />
      )}
    </>
  );
}
