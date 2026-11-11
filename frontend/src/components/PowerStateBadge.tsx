const labels: Record<string, string> = {
  poweredOn: "Online",
  poweredOff: "Offline",
  poweringOn: "Ligando",
  poweringOff: "Desligando",
  suspended: "Suspensa",
  unknown: "Desconhecido",
  not_found: "Não encontrada",
};

const colors: Record<string, string> = {
  poweredOn: "text-[var(--success)] bg-[var(--success)]/10 border-[var(--success)]/25",
  poweredOff: "text-secondary bg-[var(--glass-bg)] border-[var(--glass-border)]",
  poweringOn: "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/25",
  poweringOff: "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/25",
  suspended: "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/25",
  unknown: "text-[var(--warning)] bg-[var(--warning)]/10 border-[var(--warning)]/25",
  not_found: "text-[var(--danger)] bg-[var(--danger)]/10 border-[var(--danger)]/25",
};

export function PowerStateBadge({ powerState }: { powerState: string }) {
  return (
    <span
      className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${
        colors[powerState] || colors.unknown
      }`}
    >
      {labels[powerState] || powerState}
    </span>
  );
}
