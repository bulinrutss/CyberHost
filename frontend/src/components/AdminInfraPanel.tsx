"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminHostPanel } from "@/components/AdminHostPanel";
import { AdminMachinePanel } from "@/components/AdminMachinePanel";
import { ExpandableSection } from "@/components/ui/ExpandableSection";
import { api } from "@/lib/api";

export type InfraSection = "machine" | "esxi" | "files";

type EsxiHealth = {
  connected?: boolean;
  host?: string;
  template_found?: boolean;
  vm_count?: number;
  templates?: Array<{ label: string; template_name: string; found: boolean }>;
};

function esxiSummary(health: EsxiHealth | null, loaded: boolean): string {
  if (!loaded) return "Status do hypervisor na LAN";
  if (!health) return "Indisponível";
  const state = health.connected ? "conectado" : "offline";
  const vms = health.vm_count != null ? `${health.vm_count} VMs` : "";
  return [health.host, state, vms].filter(Boolean).join(" · ");
}

export function AdminInfraPanel({ initialSection = "machine" }: { initialSection?: InfraSection }) {
  const [open, setOpen] = useState<Record<InfraSection, boolean>>({
    machine: true,
    esxi: true,
    files: initialSection === "files",
  });
  const [health, setHealth] = useState<EsxiHealth | null>(null);
  const [healthLoaded, setHealthLoaded] = useState(false);
  const [healthError, setHealthError] = useState("");

  const toggle = (id: InfraSection) => {
    setOpen((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const loadEsxi = useCallback(async () => {
    setHealthError("");
    try {
      const next = (await api.vmwareHealth()) as EsxiHealth;
      setHealth(next);
    } catch (e) {
      setHealth(null);
      setHealthError(e instanceof Error ? e.message : "Host indisponível ou sem permissão");
    } finally {
      setHealthLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (open.esxi) void loadEsxi();
  }, [open.esxi, loadEsxi]);

  useEffect(() => {
    setOpen({
      machine: true,
      esxi: true,
      files: initialSection === "files",
    });
  }, [initialSection]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-secondary">
        Host do painel, hypervisor ESXi e arquivos/SSH desta máquina.
      </p>

      <ExpandableSection
        title="Máquina"
        summary="CPU, memória, disco e rede em tempo real"
        open={open.machine}
        onToggle={() => toggle("machine")}
      >
        {open.machine ? <AdminMachinePanel compact /> : null}
      </ExpandableSection>

      <ExpandableSection
        title="ESXi"
        summary={esxiSummary(health, healthLoaded)}
        open={open.esxi}
        onToggle={() => toggle("esxi")}
      >
        {healthError ? (
          <p className="text-sm text-[var(--danger)]">{healthError}</p>
        ) : health ? (
          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            <p>
              Estado:{" "}
              <strong className={health.connected ? "text-green-400" : "text-red-400"}>
                {health.connected ? "Conectado" : "Offline"}
              </strong>
            </p>
            <p>
              Host: <span className="font-mono">{String(health.host ?? "—")}</span>
            </p>
            <p>
              Templates:{" "}
              <strong className={health.template_found ? "text-green-400" : "text-red-400"}>
                {health.template_found ? "Todos OK" : "Faltando algum"}
              </strong>
            </p>
            <p>VMs no host: {String(health.vm_count ?? "—")}</p>
            {Array.isArray(health.templates) && (
              <ul className="sm:col-span-2 space-y-1 text-secondary">
                {health.templates.map((t) => (
                  <li key={t.template_name}>
                    {t.found ? "✓" : "✗"} {t.label} ({t.template_name})
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted">Consultando o hypervisor…</p>
        )}
      </ExpandableSection>

      <ExpandableSection
        title="Arquivos e SSH"
        summary="Disco do painel e terminal desta VM"
        open={open.files}
        onToggle={() => toggle("files")}
      >
        {open.files ? <AdminHostPanel /> : null}
      </ExpandableSection>
    </div>
  );
}
