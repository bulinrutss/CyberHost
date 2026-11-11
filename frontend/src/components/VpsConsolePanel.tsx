"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, buildConsoleWsUrl, getToken } from "@/lib/api";
import { publicAsset } from "@/lib/publicAsset";

type Props = {
  instanceId: number;
  powerState: string;
  password?: string | null;
  username?: string | null;
};

type WmksHandle = {
  connect: (url: string) => void;
  disconnect: () => void;
  destroy: () => void;
  sendCAD: () => void;
  sendInputString: (text: string) => void;
  enterFullScreen: () => void;
  exitFullScreen: () => void;
  isFullScreen: () => boolean;
  canFullScreen: () => boolean;
  setRemoteScreenSize: (width: number, height: number) => void;
  updateScreen: () => void;
  setOption?: (key: string, value: unknown) => void;
  register: (
    event: string,
    cb: (event: unknown, data: { state?: string; isFullScreen?: boolean }) => void
  ) => WmksHandle;
};

declare global {
  interface Window {
    WMKS?: {
      createWMKS: (elementId: string, options?: Record<string, unknown>) => WmksHandle;
      CONST: {
        Events: {
          CONNECTION_STATE_CHANGE: string;
          FULL_SCREEN_CHANGE: string;
        };
        ConnectionState: { CONNECTED: string; DISCONNECTED: string };
        Position?: { CENTER: number };
      };
    };
  }
}

let scriptsLoading: Promise<void> | null = null;

function loadConsoleScripts(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.WMKS) return Promise.resolve();
  if (scriptsLoading) return scriptsLoading;

  const loadScript = (src: string) =>
    new Promise<void>((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) {
        resolve();
        return;
      }
      const el = document.createElement("script");
      el.src = src;
      el.async = true;
      el.onload = () => resolve();
      el.onerror = () => reject(new Error(`Falha ao carregar ${src}`));
      document.body.appendChild(el);
    });

  const wmksCss = publicAsset("/wmks/css/wmks-all.css");
  const wmksJs = publicAsset("/wmks/wmks.min.js");

  if (!document.querySelector(`link[href="${wmksCss}"]`)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = wmksCss;
    document.head.appendChild(link);
  }

  scriptsLoading = (async () => {
    await loadScript(publicAsset("/wmks/vendor/jquery-3.7.1.min.js"));
    await loadScript(publicAsset("/wmks/vendor/jquery-ui-1.13.2.min.js"));
    await loadScript(wmksJs);
  })().catch((err) => {
    scriptsLoading = null;
    throw err;
  });

  return scriptsLoading;
}

export function VpsConsolePanel({ instanceId, powerState, password, username }: Props) {
  const containerId = `vps-console-${instanceId}`;
  const viewportRef = useRef<HTMLDivElement>(null);
  const wmksRef = useRef<WmksHandle | null>(null);
  const fullScreenRef = useRef(false);
  const connectingRef = useRef(false);
  const [status, setStatus] = useState<"idle" | "loading" | "connected" | "error">("idle");
  const [error, setError] = useState("");
  const [info, setInfo] = useState<string | null>(null);
  const [fullScreen, setFullScreen] = useState(false);

  const poweredOn = powerState === "poweredOn";

  const scheduleScreenRefresh = useCallback((wmks: WmksHandle) => {
    [0, 80, 200, 400].forEach((delay) => {
      window.setTimeout(() => {
        try {
          wmks.updateScreen();
        } catch {
          /* ignore */
        }
      }, delay);
    });
  }, []);

  const disconnect = useCallback(() => {
    const viewport = viewportRef.current;
    if (viewport && document.fullscreenElement === viewport) {
      void document.exitFullscreen().catch(() => undefined);
    }
    if (wmksRef.current) {
      try {
        wmksRef.current.disconnect();
        wmksRef.current.destroy();
      } catch {
        /* ignore */
      }
      wmksRef.current = null;
    }
    setFullScreen(false);
    fullScreenRef.current = false;
  }, []);

  const connectWithUrl = useCallback(
    (WMKS: NonNullable<typeof window.WMKS>, url: string) => {
      disconnect();
      const center = (WMKS.CONST.Position as Record<string, number> | undefined)?.LEFT_TOP;
      const wmks = WMKS.createWMKS(containerId, {
        changeResolution: true,
        rescale: true,
        ...(center !== undefined ? { position: center } : {}),
      });
      wmks.register(WMKS.CONST.Events.CONNECTION_STATE_CHANGE, (_event, data) => {
        if (data.state === WMKS.CONST.ConnectionState.CONNECTED) {
          connectingRef.current = false;
          setStatus("connected");
          setError("");
          setInfo(null);
          window.requestAnimationFrame(() => {
            scheduleScreenRefresh(wmks);
            document.getElementById(containerId)?.focus();
          });
        }
        if (data.state === WMKS.CONST.ConnectionState.DISCONNECTED) {
          connectingRef.current = false;
          setFullScreen(false);
          fullScreenRef.current = false;
          setStatus((prev) => {
            if (prev === "connected") {
              setError("Conexão com o console encerrada.");
              return "error";
            }
            if (prev === "loading") {
              setError(
                "Não foi possível conectar ao console. Confirme que o servidor está ligado e tente novamente."
              );
              return "error";
            }
            return prev;
          });
        }
      });
      wmksRef.current = wmks;
      wmks.connect(url);
    },
    [containerId, disconnect, scheduleScreenRefresh]
  );

  const connect = useCallback(async () => {
    if (!poweredOn) {
      setInfo("Ligue o servidor para abrir o console.");
      setStatus("idle");
      return;
    }

    if (connectingRef.current || !getToken()) {
      if (!getToken()) {
        setError("Faça login novamente.");
        setStatus("error");
      }
      return;
    }

    connectingRef.current = true;
    setStatus("loading");
    setError("");
    setInfo(null);

    try {
      const consoleInfo = await api.instanceConsole(instanceId);
      if (!consoleInfo.available) {
        connectingRef.current = false;
        setInfo(consoleInfo.message || "Console indisponível.");
        setStatus("idle");
        return;
      }

      await loadConsoleScripts();
      const WMKS = window.WMKS;
      if (!WMKS) throw new Error("SDK do console não carregou");

      // Proxy same-origin: ticket curto de uso único (JWT fica só no header do POST).
      const session = await api.instanceConsoleWsTicket(instanceId);
      const proxyUrl = buildConsoleWsUrl(instanceId, session.ticket);
      if (!proxyUrl) throw new Error("Faça login novamente.");

      connectWithUrl(WMKS, proxyUrl);

      window.setTimeout(() => {
        if (connectingRef.current) {
          connectingRef.current = false;
          disconnect();
          setStatus("error");
          setError(
            "Tempo esgotado ao conectar o console. Verifique se o servidor está ligado e tente de novo."
          );
        }
      }, 25000);
    } catch (e) {
      connectingRef.current = false;
      setStatus("error");
      setError(e instanceof Error ? e.message : "Erro ao conectar o console");
    }
  }, [connectWithUrl, disconnect, instanceId, poweredOn]);

  const sendCad = useCallback(() => {
    try {
      wmksRef.current?.sendCAD();
    } catch {
      setError("Não foi possível enviar Ctrl+Alt+Del.");
    }
  }, []);

  const pasteText = useCallback((text: string, label: string) => {
    const wmks = wmksRef.current;
    if (!wmks) {
      setError("Conecte o console antes de colar.");
      return;
    }
    try {
      const el = document.getElementById(containerId);
      el?.focus();
      wmks.sendInputString(text);
      setError("");
      setInfo(`${label} enviado ao console.`);
      window.setTimeout(() => setInfo(null), 2500);
    } catch {
      setError(`Não foi possível colar ${label.toLowerCase()}.`);
    }
  }, [containerId]);

  const toggleFullScreen = useCallback(() => {
    const viewport = viewportRef.current;
    const wmks = wmksRef.current;
    if (!viewport || !wmks) return;
    try {
      if (document.fullscreenElement === viewport) {
        void document.exitFullscreen();
      } else {
        void viewport.requestFullscreen();
      }
    } catch {
      setError("Tela cheia não disponível neste navegador.");
    }
  }, []);

  const disconnectSession = useCallback(() => {
    disconnect();
    connectingRef.current = false;
    setStatus("idle");
    setError("");
    setInfo("Console desconectado. Clique em Conectar para abrir novamente.");
  }, [disconnect]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const onFullScreenChange = () => {
      const isFs = document.fullscreenElement === viewport;
      fullScreenRef.current = isFs;
      setFullScreen(isFs);
      const wmks = wmksRef.current;
      if (wmks) {
        scheduleScreenRefresh(wmks);
      }
    };

    document.addEventListener("fullscreenchange", onFullScreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullScreenChange);
  }, [scheduleScreenRefresh]);

  useEffect(() => {
    if (!poweredOn) {
      disconnect();
      connectingRef.current = false;
      setStatus("idle");
      setInfo("Ligue o servidor para abrir o console.");
    }
  }, [poweredOn, disconnect]);

  useEffect(() => {
    return () => {
      connectingRef.current = false;
      disconnect();
    };
  }, [disconnect]);

  const idleMessage = !poweredOn
    ? info || "Ligue o servidor na aba Uso, controle & zona."
    : info || error || "Clique em Conectar para abrir o console da VPS.";

  return (
    <div className="glass-card overflow-hidden border border-[var(--glass-border)]">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-4 py-3 border-b border-[var(--glass-border)] bg-[var(--bg-elevated)]/60">
        <div>
          <p className="text-sm font-semibold">Console da VPS</p>
          <p className="text-xs text-muted">Tela remota do servidor</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {status === "connected" && (
            <span className="text-xs text-emerald-400 flex items-center gap-1.5 mr-1">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              Conectado
            </span>
          )}
          {status === "loading" && <span className="text-xs text-muted mr-1">Conectando…</span>}

          {status !== "connected" && status !== "loading" && (
            <button
              type="button"
              onClick={() => void connect()}
              disabled={!poweredOn}
              className="btn-primary text-sm !py-1.5 !px-4"
            >
              Conectar
            </button>
          )}

          {status === "connected" && (
            <>
              <button
                type="button"
                onClick={sendCad}
                className="btn-ghost !py-1.5 !px-3 text-xs border border-[var(--glass-border)]"
                title="Enviar Ctrl+Alt+Del para login Windows"
              >
                Ctrl+Alt+Del
              </button>
              {username && (
                <button
                  type="button"
                  onClick={() => pasteText(username, "Usuário")}
                  className="btn-ghost !py-1.5 !px-3 text-xs border border-[var(--glass-border)]"
                  title="Digitar usuário no console"
                >
                  Colar usuário
                </button>
              )}
              {password && (
                <button
                  type="button"
                  onClick={() => pasteText(password, "Senha")}
                  className="btn-ghost !py-1.5 !px-3 text-xs border border-[var(--glass-border)]"
                  title="Digitar senha no console (alternativa ao Ctrl+V)"
                >
                  Colar senha
                </button>
              )}
              <button
                type="button"
                onClick={toggleFullScreen}
                className="btn-ghost !py-1.5 !px-3 text-xs border border-[var(--glass-border)]"
              >
                {fullScreen ? "Sair tela cheia" : "Tela cheia"}
              </button>
              <button
                type="button"
                onClick={disconnectSession}
                className="btn-ghost !py-1.5 !px-3 text-xs text-[var(--warning)]"
              >
                Desconectar
              </button>
            </>
          )}

          {(status === "connected" || status === "error") && (
            <button
              type="button"
              onClick={() => void connect()}
              disabled={!poweredOn}
              className="btn-ghost !py-1.5 !px-3 text-xs"
            >
              Reconectar
            </button>
          )}
        </div>
      </div>

      <div
        ref={viewportRef}
        className="relative w-full min-h-[560px] h-[min(80vh,960px)] bg-[#0a0a0a] overflow-hidden [&:fullscreen]:min-h-0 [&:fullscreen]:h-screen [&:fullscreen]:w-screen [&:fullscreen]:max-h-none"
      >
        <div
          id={containerId}
          tabIndex={0}
          className="absolute inset-0 w-full h-full outline-none focus:ring-2 focus:ring-[var(--accent)]/40"
          onMouseDown={() => document.getElementById(containerId)?.focus()}
        />

        {status !== "connected" && status !== "loading" && (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center z-10 bg-[#0a0a0a]/85">
            <div className="max-w-sm">
              <p className="text-sm text-secondary leading-relaxed">{idleMessage}</p>
              {poweredOn && (
                <button
                  type="button"
                  onClick={() => void connect()}
                  className="btn-primary mt-5 text-sm !py-2.5 !px-6"
                >
                  Conectar console
                </button>
              )}
            </div>
          </div>
        )}

        {status === "loading" && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/70 z-10">
            <p className="text-sm text-muted">Conectando ao console…</p>
          </div>
        )}
      </div>

      {error && status === "error" && poweredOn && (
        <p className="text-xs text-[var(--danger)] px-4 py-2 border-t border-[var(--glass-border)]">
          {error}
        </p>
      )}
    </div>
  );
}
