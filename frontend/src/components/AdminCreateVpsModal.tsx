"use client";

import { useEffect, useMemo, useState } from "react";
import { AccountSearchInput } from "@/components/AccountSearchInput";
import { api, type User } from "@/lib/api";
import { BusyLabel, InlineLoader } from "@/components/PageLoader";

type Plan = {
  id: number;
  slug: string;
  name: string;
  min_vcpu: number;
  max_vcpu: number;
  min_ram_mb: number;
  max_ram_mb: number;
  default_disk_gb: number;
  max_disk_gb: number;
};

type Preset = {
  id: number;
  plan_id: number;
  name: string;
  vcpu: number;
  ram_mb: number;
  disk_gb: number;
};

type OsTemplate = {
  slug: string;
  label: string;
};

type Props = {
  open: boolean;
  users: User[];
  preselectedUserId?: number | null;
  onClose: () => void;
  onCreated: (message: string) => void;
  onError: (message: string) => void;
};

export function AdminCreateVpsModal({
  open,
  users,
  preselectedUserId,
  onClose,
  onCreated,
  onError,
}: Props) {
  const [userId, setUserId] = useState<number | null>(null);
  const [hostname, setHostname] = useState("");
  const [osSlug, setOsSlug] = useState("sv2016");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [osTemplates, setOsTemplates] = useState<OsTemplate[]>([]);
  const [planId, setPlanId] = useState<number | null>(null);
  const [presetId, setPresetId] = useState<number | null>(null);
  const [vcpu, setVcpu] = useState(2);
  const [ramGb, setRamGb] = useState(4);
  const [diskGb, setDiskGb] = useState(40);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");

  const plan = plans.find((item) => item.id === planId) || plans[0] || null;
  const planPresets = useMemo(
    () => presets.filter((item) => item.plan_id === (plan?.id ?? 0)),
    [presets, plan?.id]
  );

  useEffect(() => {
    if (!open) return;
    setUserId(preselectedUserId ?? null);
    setHostname("");
    setOsSlug("sv2016");
    setPresetId(null);
    setVcpu(2);
    setRamGb(4);
    setDiskGb(40);
    setLocalError("");
    setLoading(true);
    Promise.all([api.plans(), api.presets(), api.osTemplates()])
      .then(([planList, presetList, osList]) => {
        setPlans(planList);
        setPresets(presetList);
        setOsTemplates(osList);
        const first = planList[0];
        if (first) setPlanId(first.id);
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "Erro ao carregar planos";
        setLocalError(msg);
        onError(msg);
      })
      .finally(() => setLoading(false));

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, preselectedUserId, busy, onClose, onError]);

  if (!open) return null;

  const applyPreset = (preset: Preset) => {
    setPresetId(preset.id);
    setVcpu(preset.vcpu);
    setRamGb(preset.ram_mb / 1024);
    setDiskGb(preset.disk_gb);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userId) {
      setLocalError("Associe a VM a uma conta");
      return;
    }
    setLocalError("");
    setBusy(true);
    try {
      const order = await api.adminCreateVps({
        user_id: userId,
        hostname: hostname.trim(),
        os_template: osSlug,
        plan_id: plan?.id,
        preset_id: presetId,
        vcpu,
        ram_mb: ramGb * 1024,
        disk_gb: diskGb,
      });
      onCreated(`VM ${order.hostname} em preparação na conta selecionada`);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Não foi possível criar a VM";
      setLocalError(msg);
      onError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60"
      onClick={() => {
        if (!busy) onClose();
      }}
      role="presentation"
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-vm-title"
        className="glass-card w-full max-w-lg max-h-[90vh] overflow-y-auto p-6"
        onClick={(event) => event.stopPropagation()}
        onSubmit={submit}
      >
        <h2 id="create-vm-title" className="text-lg font-bold mb-1">
          Criar VM
        </h2>
        <p className="text-sm text-secondary mb-4">
          Clona o template no ESXi e associa à conta. Sem cobrança; o provisionamento começa na hora.
        </p>
        {loading ? (
          <InlineLoader label="Carregando planos…" />
        ) : (
          <div className="space-y-3">
            <div>
              <p className="text-xs font-medium text-secondary mb-1 uppercase tracking-wide">Conta</p>
              <AccountSearchInput
                users={users.filter((u) => u.is_active)}
                selectedId={userId}
                onSelect={(user) => setUserId(user?.id ?? null)}
              />
            </div>
            <input
              type="text"
              required
              minLength={3}
              maxLength={63}
              placeholder="Hostname (ex: cliente-web)"
              value={hostname}
              onChange={(e) => setHostname(e.target.value)}
              className="input-glass"
            />
            <label className="block text-xs">
              Sistema
              <select
                className="input-glass w-full mt-1"
                value={osSlug}
                onChange={(e) => setOsSlug(e.target.value)}
              >
                {osTemplates.map((os) => (
                  <option key={os.slug} value={os.slug}>
                    {os.label}
                  </option>
                ))}
              </select>
            </label>
            {plans.length > 1 && (
              <div className="flex gap-2">
                {plans.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`flex-1 !py-2 text-sm ${
                      plan?.id === item.id ? "btn-primary" : "btn-ghost"
                    }`}
                    onClick={() => {
                      setPlanId(item.id);
                      setPresetId(null);
                    }}
                  >
                    {item.name}
                  </button>
                ))}
              </div>
            )}
            {planPresets.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {planPresets.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    className={`btn-ghost !py-1.5 !px-3 text-xs ${
                      presetId === preset.id ? "ring-2 ring-[var(--accent)]" : ""
                    }`}
                    onClick={() => applyPreset(preset)}
                  >
                    {preset.name}
                  </button>
                ))}
              </div>
            )}
            <div className="grid grid-cols-3 gap-2">
              <label className="text-xs">
                vCPU
                <input
                  type="number"
                  min={plan?.min_vcpu ?? 1}
                  max={plan?.max_vcpu ?? 32}
                  value={vcpu}
                  onChange={(e) => {
                    setPresetId(null);
                    setVcpu(Number(e.target.value));
                  }}
                  className="input-glass w-full mt-1"
                />
              </label>
              <label className="text-xs">
                RAM (GB)
                <input
                  type="number"
                  min={(plan?.min_ram_mb ?? 1024) / 1024}
                  max={(plan?.max_ram_mb ?? 65536) / 1024}
                  value={ramGb}
                  onChange={(e) => {
                    setPresetId(null);
                    setRamGb(Number(e.target.value));
                  }}
                  className="input-glass w-full mt-1"
                />
              </label>
              <label className="text-xs">
                Disco (GB)
                <input
                  type="number"
                  min={plan?.default_disk_gb ?? 30}
                  max={plan?.max_disk_gb ?? 2000}
                  value={diskGb}
                  onChange={(e) => {
                    setPresetId(null);
                    setDiskGb(Number(e.target.value));
                  }}
                  className="input-glass w-full mt-1"
                />
              </label>
            </div>
          </div>
        )}
        {localError ? <p className="text-sm text-red-400 mt-3">{localError}</p> : null}
        <div className="flex gap-2 mt-5">
          <button type="button" className="btn-ghost flex-1" disabled={busy} onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary flex-1" disabled={busy || loading}>
            {busy ? <BusyLabel>Criando…</BusyLabel> : "Criar e provisionar"}
          </button>
        </div>
      </form>
    </div>
  );
}
