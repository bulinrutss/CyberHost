"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type HostMetrics } from "@/lib/api";
import { InlineLoader } from "@/components/PageLoader";
import { MetricRing } from "@/components/ui/MetricRing";
import { SvgChip, SvgDisk, SvgMemory, SvgRefresh, SvgServer } from "@/components/ui/svgs";

const POLL_MS = 1500;
const HISTORY = 48;

function formatBytes(n: number, digits = 1): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(digits)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(digits)} MB`;
  if (n < 1024 ** 4) return `${(n / 1024 ** 3).toFixed(digits)} GB`;
  return `${(n / 1024 ** 4).toFixed(digits)} TB`;
}

function formatRate(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${formatBytes(n, n >= 1024 ** 2 ? 1 : 0)}/s`;
}

function formatUptime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${mins}m`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

function Sparkline({ values, color = "var(--accent)" }: { values: number[]; color?: string }) {
  if (values.length < 2) {
    return <div className="h-16 rounded-lg bg-[var(--bg-elevated)]/50" />;
  }
  const max = Math.max(...values, 1);
  const w = 240;
  const h = 64;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - (v / max) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-16" preserveAspectRatio="none" aria-hidden>
      <polyline fill="none" stroke={color} strokeWidth="2" points={points} />
    </svg>
  );
}

function Bar({ percent }: { percent: number }) {
  const hot = percent >= 90;
  return (
    <div className="h-2 rounded-full bg-[var(--ring-track)] overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{
          width: `${Math.max(0, Math.min(100, percent))}%`,
          background: hot ? "var(--danger)" : "var(--accent)",
        }}
      />
    </div>
  );
}

export function AdminMachinePanel({ compact = false }: { compact?: boolean }) {
  const [snap, setSnap] = useState<HostMetrics | null>(null);
  const [error, setError] = useState("");
  const [cpuHist, setCpuHist] = useState<number[]>([]);
  const [memHist, setMemHist] = useState<number[]>([]);
  const [netHist, setNetHist] = useState<number[]>([]);
  const timer = useRef<number | null>(null);
  const inFlight = useRef(false);

  const pull = useCallback(async () => {
    if (inFlight.current || document.hidden) return;
    inFlight.current = true;
    try {
      const next = await api.adminHostMetrics();
      setSnap(next);
      setError("");
      const cpu = next.cpu.percent ?? 0;
      const mem = next.memory.percent;
      const net = next.network.reduce(
        (sum, iface) => sum + (iface.rx_bytes_per_sec ?? 0) + (iface.tx_bytes_per_sec ?? 0),
        0
      );
      setCpuHist((prev) => [...prev.slice(-(HISTORY - 1)), cpu]);
      setMemHist((prev) => [...prev.slice(-(HISTORY - 1)), mem]);
      setNetHist((prev) => [...prev.slice(-(HISTORY - 1)), net]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível ler a máquina");
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void pull();
    timer.current = window.setInterval(() => void pull(), POLL_MS);
    const onVis = () => {
      if (!document.hidden) void pull();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [pull]);

  if (!snap && !error) {
    return (
      <div className={compact ? "py-4" : "glass-card p-8"}>
        <InlineLoader label="Lendo a máquina…" />
      </div>
    );
  }

  const root = snap?.disks.find((d) => d.mount === "/") ?? snap?.disks[0];
  const updated = snap
    ? new Intl.DateTimeFormat("pt-BR", { timeStyle: "medium" }).format(new Date(snap.collected_at))
    : "";

  return (
    <div className="space-y-6">
      <div className="glass-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
          {compact ? (
            <p className="text-sm text-secondary">
              {snap?.pretty_name || snap?.kernel || "Painel"}
              {snap?.cpu.cores ? ` · ${snap.cpu.cores} núcleos` : ""}
              {snap?.architecture ? ` · ${snap.architecture}` : ""}
            </p>
          ) : (
            <div>
              <h2 className="font-semibold text-lg">Máquina do painel</h2>
              <p className="text-sm text-secondary mt-1">
                CPU, memória, disco e rede deste host — em produção, este servidor.
              </p>
            </div>
          )}
          <button type="button" className="btn-ghost !py-1.5 text-xs" onClick={() => void pull()}>
            <SvgRefresh className="w-3.5 h-3.5" /> Atualizar
          </button>
        </div>
        {error && (
          <p className="text-sm text-[var(--danger)] bg-[var(--danger)]/10 rounded-xl px-4 py-2 mb-4">{error}</p>
        )}
        {snap && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
            <p>
              <span className="text-muted">Host</span>
              <br />
              <strong className="font-mono">{snap.hostname}</strong>
            </p>
            <p>
              <span className="text-muted">Sistema</span>
              <br />
              <strong>{snap.pretty_name || snap.kernel}</strong>
            </p>
            <p>
              <span className="text-muted">Arquitetura</span>
              <br />
              <strong>{snap.architecture}</strong>
              {snap.cpu.cores ? ` · ${snap.cpu.cores} núcleos` : ""}
            </p>
            <p>
              <span className="text-muted">Uptime</span>
              <br />
              <strong>{formatUptime(snap.uptime_seconds)}</strong>
              <span className="text-muted text-xs"> · {updated}</span>
            </p>
          </div>
        )}
      </div>

      {snap && (
        <>
          <div className="glass-card p-6">
            <div className="flex flex-wrap justify-around gap-8">
              <MetricRing
                label="CPU"
                value={snap.cpu.percent}
                sublabel={
                  snap.cpu.load_1 != null
                    ? `load ${snap.cpu.load_1} / ${snap.cpu.load_5} / ${snap.cpu.load_15}`
                    : `${snap.cpu.cores} núcleos`
                }
                svg={<SvgChip className="w-4 h-4" />}
              />
              <MetricRing
                label="Memória"
                value={snap.memory.percent}
                sublabel={`${formatBytes(snap.memory.used_bytes)} / ${formatBytes(snap.memory.total_bytes)}`}
                svg={<SvgMemory className="w-4 h-4" />}
              />
              <MetricRing
                label="Disco"
                value={root?.percent}
                sublabel={
                  root
                    ? `${formatBytes(root.used_bytes)} / ${formatBytes(root.total_bytes)}`
                    : "—"
                }
                svg={<SvgDisk className="w-4 h-4" />}
              />
              <MetricRing
                label="Swap"
                value={snap.memory.swap_total_bytes ? snap.memory.swap_percent : 0}
                sublabel={
                  snap.memory.swap_total_bytes
                    ? `${formatBytes(snap.memory.swap_used_bytes)} / ${formatBytes(snap.memory.swap_total_bytes)}`
                    : "sem swap"
                }
                svg={<SvgServer className="w-4 h-4" />}
              />
            </div>
            <div className="grid sm:grid-cols-3 gap-4 mt-8">
              <div>
                <p className="text-xs text-muted mb-1">CPU (~{Math.round((HISTORY * POLL_MS) / 1000)}s)</p>
                <Sparkline values={cpuHist} />
              </div>
              <div>
                <p className="text-xs text-muted mb-1">RAM</p>
                <Sparkline values={memHist} color="var(--accent-2)" />
              </div>
              <div>
                <p className="text-xs text-muted mb-1">Rede (rx+tx)</p>
                <Sparkline values={netHist} />
              </div>
            </div>
            <div className="flex flex-wrap gap-4 mt-4 text-xs text-muted">
              <span>{snap.process_count} processos</span>
              {snap.temperature_c != null && <span>{snap.temperature_c} °C</span>}
              <span>
                Disco I/O {formatRate(snap.disk_io.read_bytes_per_sec)} lê ·{" "}
                {formatRate(snap.disk_io.write_bytes_per_sec)} grava
              </span>
            </div>
          </div>

          {snap.cpu.per_cpu.length > 1 && (
            <div className="glass-card p-6">
              <h3 className="font-semibold mb-4">Núcleos</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
                {snap.cpu.per_cpu.map((pct, idx) => (
                  <div key={idx}>
                    <p className="text-xs text-muted mb-1">
                      cpu{idx} <span className="tabular-nums">{Math.round(pct)}%</span>
                    </p>
                    <Bar percent={pct} />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="glass-card p-6">
            <h3 className="font-semibold mb-4">Discos</h3>
            <div className="space-y-4">
              {snap.disks.map((disk) => (
                <div key={disk.mount}>
                  <div className="flex flex-wrap justify-between gap-2 text-sm mb-1">
                    <span className="font-mono text-xs">
                      {disk.mount}
                      {disk.fstype ? ` · ${disk.fstype}` : ""}
                    </span>
                    <span className="text-muted tabular-nums">
                      {formatBytes(disk.used_bytes)} / {formatBytes(disk.total_bytes)} ({disk.percent}%)
                    </span>
                  </div>
                  <Bar percent={disk.percent} />
                </div>
              ))}
              {snap.disks.length === 0 && <p className="text-sm text-muted">Nenhum volume listado.</p>}
            </div>
          </div>

          <div className="glass-card p-6 overflow-x-auto">
            <h3 className="font-semibold mb-4">Rede</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted border-b border-[var(--glass-border)]">
                  <th className="pb-2">Interface</th>
                  <th className="pb-2">RX</th>
                  <th className="pb-2">TX</th>
                  <th className="pb-2">Total RX</th>
                  <th className="pb-2">Total TX</th>
                  <th className="pb-2">Erros</th>
                </tr>
              </thead>
              <tbody>
                {snap.network.map((iface) => (
                  <tr key={iface.name} className="border-b border-[var(--glass-border)]/40">
                    <td className="py-2 font-mono text-xs">{iface.name}</td>
                    <td className="py-2 tabular-nums">{formatRate(iface.rx_bytes_per_sec)}</td>
                    <td className="py-2 tabular-nums">{formatRate(iface.tx_bytes_per_sec)}</td>
                    <td className="py-2 tabular-nums text-muted">{formatBytes(iface.rx_bytes)}</td>
                    <td className="py-2 tabular-nums text-muted">{formatBytes(iface.tx_bytes)}</td>
                    <td className="py-2 tabular-nums">
                      {iface.rx_errors + iface.tx_errors + iface.rx_dropped + iface.tx_dropped || "—"}
                    </td>
                  </tr>
                ))}
                {snap.network.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-muted">
                      Sem interfaces (loopback omitido). No Windows a rede detalhada não aparece.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {snap.top_memory.length > 0 && (
            <div className="glass-card p-6 overflow-x-auto">
              <h3 className="font-semibold mb-4">Processos por memória</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-[var(--glass-border)]">
                    <th className="pb-2">PID</th>
                    <th className="pb-2">Nome</th>
                    <th className="pb-2">RSS</th>
                  </tr>
                </thead>
                <tbody>
                  {snap.top_memory.map((proc) => (
                    <tr key={proc.pid} className="border-b border-[var(--glass-border)]/40">
                      <td className="py-2 font-mono text-xs">{proc.pid}</td>
                      <td className="py-2 font-mono text-xs">{proc.name}</td>
                      <td className="py-2 tabular-nums">{formatBytes(proc.rss_bytes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
