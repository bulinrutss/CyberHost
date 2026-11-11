"use client";

import { useCallback } from "react";
import { PwaInstall } from "@/components/PwaInstall";

export function CyberHostPwa({ buttonClassName }: { buttonClassName?: string }) {
  const resolveWorker = useCallback(() => {
    const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
    if (base) return { sw: `${base}/sw.js`, scope: base };
    return { sw: "/sw.js", scope: "/" };
  }, []);

  return (
    <PwaInstall
      appName="CyberHost"
      siteHint="ruts.dev/cyberhost"
      resolveWorker={resolveWorker}
      buttonClassName={buttonClassName}
    />
  );
}
