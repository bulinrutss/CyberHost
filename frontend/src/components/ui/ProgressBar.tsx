type ProgressBarProps = {
  value: number;
  label?: string;
  showPercent?: boolean;
};

export function ProgressBar({ value, label, showPercent = true }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div className="w-full">
      {(label || showPercent) && (
        <div className="flex justify-between items-center gap-3 mb-2 text-sm">
          {label ? <span className="text-secondary">{label}</span> : <span />}
          {showPercent && (
            <span className="font-mono text-[var(--accent)] tabular-nums">{clamped}%</span>
          )}
        </div>
      )}
      <div className="metric-bar-track h-2.5">
        <div
          className="metric-bar-fill"
          style={{ width: `${clamped}%` }}
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  );
}
