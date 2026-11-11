import { ProgressBar } from "@/components/ui/ProgressBar";

type ProvisionProgressProps = {
  progress: number;
  label?: string | null;
  compact?: boolean;
  className?: string;
};

export function ProvisionProgress({
  progress,
  label,
  compact = false,
  className = "",
}: ProvisionProgressProps) {
  return (
    <div className={className}>
      {!compact && (
        <p className="text-sm text-secondary mb-3">
          {label || "Criando servidor..."} — isso pode levar alguns minutos.
        </p>
      )}
      <ProgressBar
        value={progress}
        label={compact ? label || "Criando servidor" : undefined}
        showPercent
      />
    </div>
  );
}
