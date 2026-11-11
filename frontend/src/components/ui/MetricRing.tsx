"use client";

import { useId } from "react";

type Props = {
  label: string;
  value: number | null | undefined;
  sublabel: string;
  size?: number;
  svg?: React.ReactNode;
  warnAt?: number;
};

export function MetricRing({ label, value, sublabel, size = 120, svg, warnAt = 90 }: Props) {
  const gid = useId().replace(/:/g, "");
  const pct = value ?? 0;
  const display = value != null ? `${Math.round(pct)}%` : "—";
  const stroke = 8;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  const hot = value != null && value >= warnAt;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--ring-track)"
            strokeWidth={stroke}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={hot ? "var(--danger)" : `url(#${gid})`}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={value != null ? offset : circumference}
            className="transition-all duration-700 ease-out"
          />
          <defs>
            <linearGradient id={gid} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="var(--accent)" />
              <stop offset="100%" stopColor="var(--accent-2)" />
            </linearGradient>
          </defs>
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          {svg && <div className="text-secondary mb-0.5">{svg}</div>}
          <span className="text-2xl font-bold tracking-tight tabular-nums">{display}</span>
        </div>
      </div>
      <div className="text-center">
        <p className="text-sm font-semibold">{label}</p>
        <p className="text-xs text-muted mt-0.5">{sublabel}</p>
      </div>
    </div>
  );
}
