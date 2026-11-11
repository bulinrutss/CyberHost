"use client";

import { useCallback } from "react";
import { PwaInstall } from "@/components/PwaInstall";

export function FinancePwa() {
  const resolveWorker = useCallback(() => {
    const path = window.location.pathname;
    if (path === "/financeiro" || path.startsWith("/financeiro/")) {
      return { sw: "/financeiro/sw.js", scope: "/financeiro" };
    }
    const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
    return { sw: `${base}/financeiro/sw.js`, scope: `${base}/financeiro` };
  }, []);

  return (
    <PwaInstall appName="Financeiro" siteHint="ruts.dev/financeiro" resolveWorker={resolveWorker} />
  );
}
