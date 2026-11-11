"use client";

import { Suspense } from "react";
import { SvgCloud } from "@/components/ui/svgs";
import { CloudFilesPanel } from "@/components/CloudFilesPanel";
import { PageLoader } from "@/components/PageLoader";

function CloudFilesPageContent() {
  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-10">
        <div>
          <p className="text-sm font-medium text-[var(--accent)] mb-2 tracking-wide uppercase">
            CyberCloud
          </p>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight flex items-center gap-3">
            <SvgCloud className="w-8 h-8 sm:w-10 sm:h-10 text-[var(--accent)]" />
            Meus arquivos
          </h1>
          <p className="text-secondary mt-2 max-w-xl">
            Armazene, organize e baixe seus arquivos na nuvem. Toda conta inclui 20 GB no CyberCloud
            — cada VPS ativa aumenta seu espaço.
          </p>
        </div>
      </div>

      <CloudFilesPanel />
    </>
  );
}

export default function CloudFilesPage() {
  return (
    <Suspense fallback={<PageLoader label="Carregando arquivos…" />}>
      <CloudFilesPageContent />
    </Suspense>
  );
}
