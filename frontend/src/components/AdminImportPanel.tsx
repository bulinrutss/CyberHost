"use client";

import { useState } from "react";
import { AccountSearchInput } from "@/components/AccountSearchInput";
import { api, type User } from "@/lib/api";
import { formatPhoneDisplay } from "@/lib/phone";
import { BusyLabel } from "@/components/PageLoader";

type DiscoverVm = {
  vm_name: string;
  hostname: string;
  suggested_name: string;
  vcpu: number;
  ram_mb: number;
  disk_gb: number;
  ip_address: string | null;
  power_state: string;
  suggested_plan_slug: string;
};

type ImportRow = DiscoverVm & {
  selected: boolean;
  userId: number | null;
};

type ImportResult = {
  vm_name: string;
  user_id: number;
  phone: string;
  name: string;
  email?: string | null;
};

export function AdminImportPanel() {
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [alreadyRegistered, setAlreadyRegistered] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<ImportResult[]>([]);
  const [importErrors, setImportErrors] = useState<Array<{ vm_name: string; error: string }>>([]);

  const discover = async () => {
    setLoading(true);
    setError("");
    setResults([]);
    setImportErrors([]);
    try {
      const [data, accountList] = await Promise.all([api.adminDiscoverVms(), api.adminUsers()]);
      setUsers(accountList.filter((u) => !u.is_admin));
      setAlreadyRegistered(data.already_registered);
      setRows(
        data.unregistered.map((vm) => ({
          ...vm,
          selected: true,
          userId: null,
        }))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao buscar VMs");
    } finally {
      setLoading(false);
    }
  };

  const updateRow = (vmName: string, patch: Partial<ImportRow>) => {
    setRows((prev) => prev.map((r) => (r.vm_name === vmName ? { ...r, ...patch } : r)));
  };

  const selectedRows = rows.filter((r) => r.selected);

  const importSelected = async () => {
    const toImport = selectedRows.filter((r) => r.userId);
    if (toImport.length === 0) {
      setError("Selecione VMs e escolha a conta de cada cliente (já cadastrada)");
      return;
    }
    if (toImport.length !== selectedRows.length) {
      setError("Toda VM selecionada precisa de uma conta existente");
      return;
    }

    setImporting(true);
    setError("");
    try {
      const res = await api.adminImportVms({
        vms: toImport.map((r) => ({
          vm_name: r.vm_name,
          user_id: r.userId as number,
          plan_slug: r.suggested_plan_slug,
        })),
      });
      setResults(res.imported);
      setImportErrors(res.errors);
      setRows((prev) => prev.filter((r) => !res.imported.some((i) => i.vm_name === r.vm_name)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao importar");
    } finally {
      setImporting(false);
    }
  };

  const summaryText = results
    .map((r) => `${r.name} — ${r.vm_name}\nTelefone: ${formatPhoneDisplay(r.phone)}${r.email ? `\nE-mail: ${r.email}` : ""}`)
    .join("\n\n");

  return (
    <div className="space-y-6">
      <div className="glass-card p-6">
        <h2 className="font-semibold mb-2">Importar servidores existentes</h2>
        <p className="text-secondary text-sm mb-4">
          Detecta servidores com nome começando em <code className="text-[var(--accent)]">VPS</code>{" "}
          (ex.: VPS-cliente, VPS Cliente) que ainda não estão no painel. Vincule cada VM a uma conta já
          cadastrada — busque por nome, telefone ou e-mail.
        </p>
        <button type="button" onClick={discover} disabled={loading} className="btn-primary !py-2">
          {loading ? <BusyLabel>Buscando servidores…</BusyLabel> : "Detectar VMs"}
        </button>
        {alreadyRegistered.length > 0 && (
          <p className="text-xs text-muted mt-3">Já no painel: {alreadyRegistered.join(", ")}</p>
        )}
      </div>

      {rows.length > 0 && (
        <div className="glass-card p-6 overflow-visible">
          <div className="flex flex-wrap gap-4 justify-between items-end mb-4">
            <p className="text-sm text-secondary">{rows.length} VM(s) pronta(s) para importar</p>
            <button
              type="button"
              onClick={importSelected}
              disabled={importing || selectedRows.length === 0}
              className="btn-primary !py-2"
            >
              {importing ? "Importando..." : `Importar ${selectedRows.length} selecionada(s)`}
            </button>
          </div>

          <div className="overflow-x-auto overflow-y-visible">
            <table className="w-full text-sm min-w-[720px]">
              <thead>
                <tr className="text-left text-muted border-b border-[var(--glass-border)]">
                  <th className="pb-2 pr-2 w-8" />
                  <th className="pb-2 pr-3">VM</th>
                  <th className="pb-2 pr-3">Recursos</th>
                  <th className="pb-2">Conta do cliente</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.vm_name} className="border-b border-[var(--glass-border)]/50">
                    <td className="py-3 pr-2 align-top">
                      <input
                        type="checkbox"
                        checked={row.selected}
                        onChange={(e) => updateRow(row.vm_name, { selected: e.target.checked })}
                      />
                    </td>
                    <td className="py-3 pr-3 align-top">
                      <p className="font-medium">{row.vm_name}</p>
                      {row.ip_address && <p className="text-xs text-muted font-mono">{row.ip_address}</p>}
                    </td>
                    <td className="py-3 pr-3 text-secondary align-top">
                      {row.vcpu} vCPU · {row.ram_mb / 1024} GB · {row.disk_gb} GB
                      <span className="block text-xs text-muted">{row.suggested_plan_slug}</span>
                    </td>
                    <td className="py-3 align-top">
                      <AccountSearchInput
                        users={users}
                        selectedId={row.userId}
                        onSelect={(user) => updateRow(row.vm_name, { userId: user?.id ?? null })}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {error && (
        <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-2">{error}</p>
      )}

      {results.length > 0 && (
        <div className="glass-card p-6">
          <h3 className="font-semibold mb-2 text-[var(--success)]">{results.length} VM(s) vinculada(s)</h3>
          <p className="text-xs text-muted mb-3">A senha de login do painel não muda — a conta já existia.</p>
          <pre className="text-xs bg-[var(--bg-elevated)] rounded-xl p-4 overflow-x-auto whitespace-pre-wrap font-mono">
            {summaryText}
          </pre>
          <button
            type="button"
            className="btn-ghost mt-3 !py-2 text-sm"
            onClick={() => navigator.clipboard.writeText(summaryText)}
          >
            Copiar resumo
          </button>
        </div>
      )}

      {importErrors.length > 0 && (
        <div className="glass-card p-6 border border-[var(--danger)]/30">
          <h3 className="font-semibold text-[var(--danger)] mb-2">Erros na importação</h3>
          <ul className="text-sm space-y-1">
            {importErrors.map((e) => (
              <li key={e.vm_name}>
                <strong>{e.vm_name}:</strong> {e.error}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
