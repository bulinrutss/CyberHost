"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { api, formatPrice, type AdminStats } from "@/lib/api";
import { formatPhoneDisplay } from "@/lib/phone";
import { InlineLoader } from "@/components/PageLoader";
import { VpsStatusBadge } from "@/components/VpsStatusBadge";
import { SvgChevronDown } from "@/components/ui/svgs";
import { AdminTrafficPanel } from "@/components/AdminTrafficPanel";

type Days = 7 | 30 | 90;
type EventFilter = "all" | "error" | "warning" | "pending";
type StatsView = "ops" | "traffic";

const SERIES = [
  { key: "completed" as const, label: "Concluídos", color: "var(--success)" },
  { key: "pending" as const, label: "Pendentes", color: "#38bdf8" },
  { key: "denied" as const, label: "Negados", color: "var(--warning)" },
  { key: "error" as const, label: "Erros", color: "var(--danger)" },
];

const STATUS_LABEL: Record<string, string> = {
  pending_payment: "Aguardando pagamento",
  paid: "Pago",
  provisioning: "Em preparação",
  active: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
  running: "Ligada",
  stopped: "Desligada",
  error: "Erro",
  creating: "Criando",
  configuring: "Configurando",
  suspended: "Suspenso",
};

const KIND_LABEL: Record<string, string> = {
  vps: "VPS",
  cloud: "CyberCloud",
  game: "Game",
  machine: "Máquina",
};

function formatBytes(n: number) {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${n} B`;
}

function formatDay(iso: string) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function formatWhen(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(
    new Date(value)
  );
}

function ExpandableSection({
  title,
  summary,
  open,
  onToggle,
  children,
}: {
  title: string;
  summary?: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="glass-card overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 p-5 text-left hover:bg-[var(--bg-elevated)]/40 transition"
      >
        <div className="min-w-0">
          <p className="font-medium">{title}</p>
          {summary ? <p className="text-xs text-muted truncate mt-0.5">{summary}</p> : null}
        </div>
        <SvgChevronDown
          className={`w-4 h-4 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open ? (
        <div className="px-5 pb-5 border-t border-[var(--glass-border)] pt-4">{children}</div>
      ) : null}
    </div>
  );
}

function Kpi({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "ok" | "warn" | "bad";
}) {
  const color =
    tone === "ok" ? "text-[var(--success)]" : tone === "warn" ? "text-[var(--warning)]" : tone === "bad" ? "text-[var(--danger)]" : "";
  return (
    <div className="glass-card p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className={`text-2xl font-semibold mt-1 tabular-nums ${color}`}>{value}</p>
      {hint ? <p className="text-xs text-muted mt-1">{hint}</p> : null}
    </div>
  );
}

function StackedBars({
  days,
}: {
  days: AdminStats["daily"];
}) {
  const max = Math.max(1, ...days.map((day) => day.total));
  const barW = Math.max(6, Math.min(18, 560 / Math.max(days.length, 1) - 4));
  const width = Math.max(560, days.length * (barW + 4));
  const height = 180;
  const chartH = 150;
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full min-w-[520px] h-[200px]">
        {days.map((day, index) => {
          const x = index * (barW + 4) + 8;
          let y = chartH;
          const segments = SERIES.map((serie) => ({ ...serie, value: day[serie.key] })).filter(
            (s) => s.value > 0
          );
          return (
            <g key={day.date}>
              {segments.map((seg) => {
                const h = (seg.value / max) * chartH;
                y -= h;
                const rect = (
                  <rect
                    key={seg.key}
                    x={x}
                    y={y}
                    width={barW}
                    height={Math.max(h, 0)}
                    fill={seg.color}
                    rx={1}
                  >
                    <title>{`${formatDay(day.date)} · ${seg.label}: ${seg.value}`}</title>
                  </rect>
                );
                return rect;
              })}
              {index % Math.ceil(days.length / 8) === 0 ? (
                <text
                  x={x + barW / 2}
                  y={height - 4}
                  textAnchor="middle"
                  className="fill-current"
                  fill="currentColor"
                  fontSize="10"
                  opacity={0.6}
                >
                  {formatDay(day.date)}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function Donut({
  slices,
}: {
  slices: Array<{ label: string; value: number; color: string }>;
}) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  const r = 42;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="flex items-center gap-5">
      <svg width="120" height="120" viewBox="0 0 120 120" className="-rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--ring-track)" strokeWidth="14" />
        {total === 0 ? null : (
          slices
            .filter((s) => s.value > 0)
            .map((slice) => {
              const len = (slice.value / total) * c;
              const node = (
                <circle
                  key={slice.label}
                  cx="60"
                  cy="60"
                  r={r}
                  fill="none"
                  stroke={slice.color}
                  strokeWidth="14"
                  strokeDasharray={`${len} ${c - len}`}
                  strokeDashoffset={-offset}
                >
                  <title>{`${slice.label}: ${slice.value}`}</title>
                </circle>
              );
              offset += len;
              return node;
            })
        )}
      </svg>
      <ul className="space-y-1 text-sm">
        {slices.map((slice) => (
          <li key={slice.label} className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: slice.color }} />
            <span className="text-secondary">
              {slice.label} <strong className="text-primary">{slice.value}</strong>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Meter({ label, value, suffix }: { label: string; value: number; suffix: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted">{label}</span>
        <span className="tabular-nums">
          {value.toLocaleString("pt-BR")} {suffix}
        </span>
      </div>
      <div className="h-2 rounded-full bg-[var(--ring-track)] overflow-hidden">
        <div
          className="h-full rounded-full bg-[var(--accent)]"
          style={{ width: `${Math.min(100, 12 + Math.log10(Math.max(value, 1)) * 28)}%` }}
        />
      </div>
    </div>
  );
}

export function AdminStatsPanel() {
  const [view, setView] = useState<StatsView>("ops");
  const [days, setDays] = useState<Days>(30);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [eventFilter, setEventFilter] = useState<EventFilter>("all");
  const [deletingEvent, setDeletingEvent] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [openSections, setOpenSections] = useState({
    clients: false,
    machines: false,
    events: false,
  });

  const load = useCallback(async (window: Days) => {
    setLoading(true);
    setError("");
    try {
      setStats(await api.adminStats(window));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível carregar as estatísticas");
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === "ops") void load(days);
  }, [days, load, view]);

  const events = useMemo(() => {
    if (!stats) return [];
    if (eventFilter === "all") return stats.events;
    return stats.events.filter((item) => item.level === eventFilter);
  }, [stats, eventFilter]);

  const deleteEvent = async (event: AdminStats["events"][number], index: number) => {
    if (!event.can_delete) return;
    const isMachine = event.source === "machine";
    if (
      !window.confirm(
        isMachine
          ? "Limpar este alerta da máquina?"
          : "Apagar este pedido do histórico e das métricas? A VPS continua no ar; só some o valor deste pedido."
      )
    ) {
      return;
    }
    const key = `${event.source}-${event.order_id ?? event.instance_id ?? index}-${event.at}`;
    setDeletingEvent(key);
    setError("");
    setNotice("");
    try {
      if (isMachine && event.instance_id) {
        await api.adminClearMachineError(event.instance_id);
        setNotice("Alerta da máquina removido");
      } else if (
        event.order_id &&
        (event.source === "vps" || event.source === "cloud" || event.source === "game")
      ) {
        await api.adminDeleteOrder(event.source, event.order_id);
        setNotice("Pedido apagado");
      } else {
        throw new Error("Este evento não pode ser apagado");
      }
      await load(days);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível apagar o evento");
    } finally {
      setDeletingEvent(null);
    }
  };

  const toolbar = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="font-semibold text-lg">Supervisão</h2>
        {view === "ops" && stats ? (
          <p className="text-xs text-muted">
            Atualizado {formatWhen(stats.generated_at)} · pedidos dos últimos {stats.days} dias
          </p>
        ) : (
          <p className="text-xs text-muted">Pedidos e uso do painel</p>
        )}
        {view === "ops" && error ? <p className="text-xs text-red-400 mt-1">{error}</p> : null}
        {notice ? <p className="text-xs text-[var(--success)] mt-1">{notice}</p> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {(
          [
            ["ops", "Pedidos"],
            ["traffic", "Acessos"],
          ] as Array<[StatsView, string]>
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            data-track={`stats-aba-${id}`}
            onClick={() => setView(id)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium ${
              view === id ? "btn-primary !py-1.5" : "btn-ghost !py-1.5"
            }`}
          >
            {label}
          </button>
        ))}
        {([7, 30, 90] as Days[]).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setDays(option)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium ${
              days === option ? "btn-primary !py-1.5" : "btn-ghost !py-1.5"
            }`}
          >
            {option} dias
          </button>
        ))}
      </div>
    </div>
  );

  if (view === "traffic") {
    return (
      <div className="space-y-6">
        {toolbar}
        <AdminTrafficPanel days={days} />
      </div>
    );
  }

  if (loading && !stats) {
    return (
      <div className="space-y-6">
        {toolbar}
        <InlineLoader label="Carregando estatísticas…" />
      </div>
    );
  }
  if (error && !stats) {
    return (
      <div className="space-y-6">
        {toolbar}
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    );
  }
  if (!stats) return null;

  const orderSlices = SERIES.map((s) => ({
    label: s.label,
    value: stats.orders[s.key],
    color: s.color,
  }));
  const vpsSlices = [
    { label: "Ligadas", value: stats.host.vps_running, color: "var(--success)" },
    { label: "Desligadas", value: stats.host.vps_stopped, color: "#64748b" },
    { label: "Erro", value: stats.host.vps_error, color: "var(--danger)" },
    {
      label: "Outras",
      value: Math.max(
        0,
        stats.host.vps_total - stats.host.vps_running - stats.host.vps_stopped - stats.host.vps_error
      ),
      color: "#38bdf8",
    },
  ];

  return (
    <div className="space-y-6">
      {toolbar}

      {error ? <p className="text-red-400 text-sm">{error}</p> : null}

      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <Kpi
          label="Pedidos no período"
          value={String(stats.orders.total)}
          hint={`${stats.orders.completed} concluídos · ${stats.orders.pending} pendentes`}
        />
        <Kpi
          label="Concluídos / pagos"
          value={String(stats.orders.completed)}
          hint={formatPrice(stats.orders.revenue_cents)}
          tone="ok"
        />
        <Kpi
          label="Negados"
          value={String(stats.orders.denied)}
          hint="Cancelados pelo cliente ou expirados"
          tone={stats.orders.denied ? "warn" : undefined}
        />
        <Kpi
          label="Erros"
          value={String(stats.orders.error)}
          hint={`${stats.host.vps_error} máquina(s) em erro`}
          tone={stats.orders.error || stats.host.vps_error ? "bad" : undefined}
        />
        <Kpi
          label="Clientes"
          value={String(stats.clients.total)}
          hint={`${stats.clients.active} ativos · ${stats.clients.admins} admin`}
        />
        <Kpi
          label="VPS no servidor"
          value={`${stats.host.vps_running}/${stats.host.vps_total}`}
          hint={`${stats.host.vps_stopped} desligadas · ${stats.host.vps_suspended} suspensas`}
        />
        <Kpi
          label="Capacidade alocada"
          value={`${stats.host.allocated_vcpu} vCPU`}
          hint={`${(stats.host.allocated_ram_mb / 1024).toFixed(0)} GB RAM · ${stats.host.allocated_disk_gb} GB disco`}
        />
        <Kpi
          label="CyberCloud"
          value={formatBytes(stats.host.cloud_used_bytes)}
          hint={`${stats.host.cloud_files} arquivos · ${stats.host.cloud_contracted_gb} GB contratados`}
        />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <section className="glass-card p-5 lg:col-span-2">
          <h3 className="font-medium mb-1">Pedidos por dia</h3>
          <p className="text-xs text-muted mb-3">Concluídos, pendentes, negados e erros</p>
          <StackedBars days={stats.daily} />
          <div className="flex flex-wrap gap-4 mt-2 text-xs text-secondary">
            {SERIES.map((s) => (
              <span key={s.key} className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
                {s.label}
              </span>
            ))}
          </div>
        </section>
        <section className="glass-card p-5 space-y-6">
          <div>
            <h3 className="font-medium mb-3">Resultado dos pedidos</h3>
            <Donut slices={orderSlices} />
          </div>
          <div>
            <h3 className="font-medium mb-3">Estado das VPS</h3>
            <Donut slices={vpsSlices} />
          </div>
        </section>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <section className="glass-card p-5 space-y-4">
          <h3 className="font-medium">Uso do servidor</h3>
          <Meter label="vCPU alocada" value={stats.host.allocated_vcpu} suffix="núcleos" />
          <Meter
            label="RAM alocada"
            value={Math.round(stats.host.allocated_ram_mb / 1024)}
            suffix="GB"
          />
          <Meter label="Disco alocado" value={stats.host.allocated_disk_gb} suffix="GB" />
          <div className="grid grid-cols-2 gap-3 text-sm pt-2">
            <p className="text-secondary">
              Mix:{" "}
              {Object.entries(stats.orders.by_kind)
                .map(([kind, count]) => `${KIND_LABEL[kind] ?? kind} ${count}`)
                .join(" · ") || "—"}
            </p>
            <p className="text-secondary text-right">
              {stats.host.game_servers} servidor(es) de game
            </p>
          </div>
        </section>
        <section className="glass-card p-5">
          <h3 className="font-medium mb-3">Receita concluída no período</h3>
          <p className="text-3xl font-semibold tabular-nums">{formatPrice(stats.orders.revenue_cents)}</p>
          <p className="text-xs text-muted mt-2 mb-4">Soma dos pedidos pagos ou concluídos</p>
          <div className="h-[88px]">
            <svg viewBox={`0 0 ${Math.max(stats.daily.length, 2) * 12} 88`} className="w-full h-full">
              {(() => {
                const maxRev = Math.max(1, ...stats.daily.map((d) => d.revenue_cents));
                const pts = stats.daily.map((d, i) => {
                  const x = i * 12 + 4;
                  const y = 80 - (d.revenue_cents / maxRev) * 70;
                  return `${x},${y}`;
                });
                return (
                  <>
                    <polyline
                      fill="none"
                      stroke="var(--accent)"
                      strokeWidth="2"
                      points={pts.join(" ")}
                    />
                    {stats.daily.map((d, i) => (
                      <circle
                        key={d.date}
                        cx={i * 12 + 4}
                        cy={80 - (d.revenue_cents / maxRev) * 70}
                        r="2"
                        fill="var(--accent)"
                      >
                        <title>{`${formatDay(d.date)} · ${formatPrice(d.revenue_cents)}`}</title>
                      </circle>
                    ))}
                  </>
                );
              })()}
            </svg>
          </div>
        </section>
      </div>

      <ExpandableSection
        title="Clientes"
        summary={`${stats.clients.total} cliente(s) · ${stats.top_clients.length} na lista`}
        open={openSections.clients}
        onToggle={() => setOpenSections((s) => ({ ...s, clients: !s.clients }))}
      >
        <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted uppercase tracking-wide sticky top-0 bg-[var(--bg-elevated)]">
              <tr className="text-left">
                <th className="py-2 pr-3">Cliente</th>
                <th className="py-2 pr-3">VPS</th>
                <th className="py-2 pr-3">Pedidos</th>
                <th className="py-2 pr-3">Faturado</th>
                <th className="py-2">Alertas</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_clients.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-secondary">
                    Nenhum cliente no período.
                  </td>
                </tr>
              ) : (
                stats.top_clients.map((client) => (
                  <tr key={client.id} className="border-t border-[var(--glass-border)]">
                    <td className="py-2.5 pr-3">
                      <p className="font-medium">{client.name}</p>
                      <p className="text-xs text-muted">{formatPhoneDisplay(client.phone)}</p>
                    </td>
                    <td className="py-2.5 pr-3 tabular-nums">
                      {client.vps_running}/{client.vps_count}
                      {client.vps_error ? (
                        <span className="text-[var(--danger)]"> · {client.vps_error} erro</span>
                      ) : null}
                    </td>
                    <td className="py-2.5 pr-3 tabular-nums">{client.orders}</td>
                    <td className="py-2.5 pr-3 tabular-nums">{formatPrice(client.spent_cents)}</td>
                    <td className="py-2.5 text-xs">
                      {client.order_errors ? (
                        <span className="text-[var(--danger)]">{client.order_errors} pedido(s) com erro</span>
                      ) : null}
                      {client.cloud_suspended ? (
                        <span className="text-[var(--warning)]"> CyberCloud suspenso</span>
                      ) : null}
                      {!client.is_active ? <span className="text-muted"> Inativo</span> : null}
                      {!client.order_errors && !client.cloud_suspended && client.is_active ? (
                        <span className="text-muted">—</span>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </ExpandableSection>

      <ExpandableSection
        title="Máquinas"
        summary={`${stats.host.vps_total} VPS · ${stats.host.vps_running} ligadas · ${stats.host.vps_error} em erro`}
        open={openSections.machines}
        onToggle={() => setOpenSections((s) => ({ ...s, machines: !s.machines }))}
      >
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted uppercase tracking-wide sticky top-0 bg-[var(--bg-elevated)]">
              <tr className="text-left">
                <th className="py-2 pr-3">Máquina</th>
                <th className="py-2 pr-3">Cliente</th>
                <th className="py-2 pr-3">Recursos</th>
                <th className="py-2 pr-3">Estado</th>
                <th className="py-2">Detalhe</th>
              </tr>
            </thead>
            <tbody>
              {stats.machines.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-secondary">
                    Nenhuma VPS cadastrada.
                  </td>
                </tr>
              ) : (
                stats.machines.map((vm) => (
                  <tr key={vm.id} className="border-t border-[var(--glass-border)] align-top">
                    <td className="py-2.5 pr-3">
                      <Link href={`/admin/vps/${vm.id}`} className="font-medium text-[var(--accent)] hover:underline">
                        {vm.vm_name}
                      </Link>
                      {vm.ip_address ? (
                        <p className="text-xs font-mono text-muted">{vm.ip_address}</p>
                      ) : null}
                    </td>
                    <td className="py-2.5 pr-3">
                      <p>{vm.user_name}</p>
                      <p className="text-xs text-muted">{formatPhoneDisplay(vm.user_phone)}</p>
                    </td>
                    <td className="py-2.5 pr-3 text-xs text-secondary">
                      {vm.vcpu} vCPU · {vm.ram_mb / 1024} GB · {vm.disk_gb} GB
                      {vm.paid_until ? (
                        <p className="text-muted">
                          Vence {new Date(vm.paid_until).toLocaleDateString("pt-BR")}
                        </p>
                      ) : null}
                    </td>
                    <td className="py-2.5 pr-3">
                      <VpsStatusBadge status={vm.status} />
                      {vm.suspended_for_billing ? (
                        <p className="text-[10px] text-[var(--warning)] mt-1">Billing suspenso</p>
                      ) : null}
                    </td>
                    <td className="py-2.5 text-xs text-red-400 max-w-[280px] break-words">
                      {vm.error_message || "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </ExpandableSection>

      <ExpandableSection
        title="Registro de eventos"
        summary={`${stats.events.length} evento(s)`}
        open={openSections.events}
        onToggle={() => setOpenSections((s) => ({ ...s, events: !s.events }))}
      >
        <div className="flex flex-wrap gap-2 mb-3">
          {(
            [
              ["all", "Todos"],
              ["error", "Erros"],
              ["warning", "Negados / alertas"],
              ["pending", "Pendentes"],
            ] as Array<[EventFilter, string]>
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setEventFilter(id)}
              className={`px-3 py-1 rounded-lg text-xs ${
                eventFilter === id ? "btn-primary !py-1" : "btn-ghost !py-1"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="space-y-2 max-h-[480px] overflow-y-auto">
          {events.length === 0 ? (
            <p className="text-secondary text-sm py-6">Nenhum evento neste filtro.</p>
          ) : (
            events.map((event, index) => {
              const key = `${event.source}-${event.order_id ?? event.instance_id ?? index}-${event.at}`;
              return (
              <article
                key={key}
                className="rounded-xl border border-[var(--glass-border)] p-3"
              >
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="text-sm font-medium">
                    {KIND_LABEL[event.source] ?? event.source} · {event.title}
                  </p>
                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border ${
                        event.level === "error"
                          ? "text-red-400 border-red-500/30"
                          : event.level === "warning"
                            ? "text-amber-400 border-amber-500/30"
                            : event.level === "pending"
                              ? "text-sky-400 border-sky-500/30"
                              : "text-muted border-[var(--glass-border)]"
                      }`}
                    >
                      {STATUS_LABEL[event.status] ?? event.status}
                    </span>
                    {event.can_delete ? (
                      <button
                        type="button"
                        disabled={deletingEvent === key}
                        onClick={() => void deleteEvent(event, index)}
                        className="btn-ghost text-xs !py-1 !px-2 !text-[var(--danger)] !border-[var(--danger)]/30 hover:!bg-[var(--danger)]/10"
                      >
                        {deletingEvent === key ? "…" : "Apagar"}
                      </button>
                    ) : null}
                  </div>
                </div>
                <p className="text-xs text-secondary mt-1">
                  {event.user_name} · {formatPhoneDisplay(event.user_phone)}
                  {event.subject ? ` · ${event.subject}` : ""}
                  {event.total_cents ? ` · ${formatPrice(event.total_cents)}` : ""}
                </p>
                {event.detail ? (
                  <p className="text-xs text-red-400 mt-1 break-words">{event.detail}</p>
                ) : null}
                <p className="text-[11px] text-muted mt-1">{formatWhen(event.at)}</p>
              </article>
              );
            })
          )}
        </div>
      </ExpandableSection>
    </div>
  );
}
