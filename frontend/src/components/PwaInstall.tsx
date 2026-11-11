"use client";

import { useEffect, useState } from "react";
import { SvgDownload } from "@/components/ui/svgs";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

type Props = {
  appName: string;
  siteHint: string;
  resolveWorker: () => { sw: string; scope: string };
  buttonClassName?: string;
};

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const nav = window.navigator as Navigator & { standalone?: boolean };
  return window.matchMedia("(display-mode: standalone)").matches || nav.standalone === true;
}

function isIosDevice(): boolean {
  const ua = window.navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function isIosSafari(): boolean {
  const ua = window.navigator.userAgent;
  if (!isIosDevice()) return false;
  return /Safari/.test(ua) && !/CriOS|FxiOS|OPiOS|EdgiOS/.test(ua);
}

export function PwaInstall({ appName, siteHint, resolveWorker, buttonClassName = "btn-ghost !py-2 text-sm" }: Props) {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [standalone, setStandalone] = useState(false);
  const [iosSafari, setIosSafari] = useState(false);
  const [iosOther, setIosOther] = useState(false);
  const [guide, setGuide] = useState<"safari" | "chrome" | null>(null);

  useEffect(() => {
    setStandalone(isStandalone());
    setIosSafari(isIosSafari() && !isStandalone());
    setIosOther(isIosDevice() && !isIosSafari() && !isStandalone());

    const onPrompt = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);

    const { sw, scope } = resolveWorker();
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register(sw, { scope }).catch(() => {
        /* browser use is unchanged if install extras fail */
      });
    }

    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, [resolveWorker]);

  const install = async () => {
    if (!installEvent) return;
    await installEvent.prompt();
    await installEvent.userChoice;
    setInstallEvent(null);
  };

  if (standalone) return null;

  return (
    <>
      {installEvent && (
        <button type="button" className={buttonClassName} onClick={() => void install()}>
          <SvgDownload className="w-4 h-4" />
          Instalar app
        </button>
      )}
      {iosSafari && (
        <button type="button" className={buttonClassName} onClick={() => setGuide("safari")}>
          <IosShareIcon />
          Tela inicial
        </button>
      )}
      {iosOther && (
        <button type="button" className={buttonClassName} onClick={() => setGuide("chrome")}>
          <IosShareIcon />
          No iPhone
        </button>
      )}
      {guide && (
        <div className="fin-modal-backdrop" onClick={() => setGuide(null)} role="presentation">
          <div className="glass-card fin-modal" onClick={(e) => e.stopPropagation()}>
            {guide === "safari" ? (
              <>
                <h2 className="text-lg font-semibold mb-2">Colocar na tela inicial</h2>
                <p className="text-sm text-secondary mb-4">
                  No iPhone isso só dá pelo Safari. Depois o ícone abre como aplicativo; o site no Safari continua
                  igual.
                </p>
                <ol className="space-y-3 text-sm">
                  <li className="flex gap-3">
                    <span className="fin-chip !px-2 !py-0.5 shrink-0">1</span>
                    <span>
                      Toque em <strong>Compartilhar</strong>{" "}
                      <IosShareIcon className="inline w-4 h-4 align-text-bottom" /> (quadrado com a seta para cima),
                      na barra de baixo do Safari.
                    </span>
                  </li>
                  <li className="flex gap-3">
                    <span className="fin-chip !px-2 !py-0.5 shrink-0">2</span>
                    <span>
                      Role a lista e toque em <strong>Adicionar à Tela de Início</strong>.
                    </span>
                  </li>
                  <li className="flex gap-3">
                    <span className="fin-chip !px-2 !py-0.5 shrink-0">3</span>
                    <span>
                      Toque em <strong>Adicionar</strong>. O ícone <strong>{appName}</strong> aparece junto dos outros
                      apps.
                    </span>
                  </li>
                </ol>
              </>
            ) : (
              <>
                <h2 className="text-lg font-semibold mb-2">No iPhone use o Safari</h2>
                <p className="text-sm text-secondary mb-4">
                  Chrome, Instagram e outros apps do iPhone não deixam instalar. Abra o {appName} no Safari e depois
                  coloque na tela inicial.
                </p>
                <ol className="space-y-3 text-sm">
                  <li className="flex gap-3">
                    <span className="fin-chip !px-2 !py-0.5 shrink-0">1</span>
                    <span>
                      Copie o endereço: <strong>{siteHint}</strong>
                    </span>
                  </li>
                  <li className="flex gap-3">
                    <span className="fin-chip !px-2 !py-0.5 shrink-0">2</span>
                    <span>
                      Abra o <strong>Safari</strong> e cole o link.
                    </span>
                  </li>
                  <li className="flex gap-3">
                    <span className="fin-chip !px-2 !py-0.5 shrink-0">3</span>
                    <span>
                      Compartilhar → <strong>Adicionar à Tela de Início</strong>.
                    </span>
                  </li>
                </ol>
              </>
            )}
            <div className="flex justify-end mt-6">
              <button type="button" className="btn-primary" onClick={() => setGuide(null)}>
                Entendi
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function IosShareIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 16V4m0 0l-4 4m4-4l4 4" />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.75}
        d="M5 14v4.5A2.5 2.5 0 007.5 21h9a2.5 2.5 0 002.5-2.5V14"
      />
    </svg>
  );
}
