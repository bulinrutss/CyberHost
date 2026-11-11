const statusColors: Record<string, string> = {
  running: "text-[var(--success)] bg-[var(--success)]/10 border-[var(--success)]/20",
  creating: "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/20",
  configuring: "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/20",
  stopped: "text-secondary bg-[var(--glass-bg)] border-[var(--glass-border)]",
  error: "text-[var(--danger)] bg-[var(--danger)]/10 border-[var(--danger)]/20",
  deleted: "text-muted bg-[var(--glass-bg)] border-[var(--glass-border)]",
};

const statusLabels: Record<string, string> = {
  running: "Ativa",
  creating: "Criando",
  configuring: "Configurando",
  stopped: "Parada",
  error: "Erro",
  deleted: "Removida",
};

export function VpsStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`px-2.5 py-1 rounded-full text-xs font-medium border ${
        statusColors[status] || statusColors.stopped
      }`}
    >
      {statusLabels[status] || status}
    </span>
  );
}
