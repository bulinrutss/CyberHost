"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Status = "off" | "on" | "blocked" | "unsupported" | "busy";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

export function FinancePushToggle({ vapidPublicKey }: { vapidPublicKey: string }) {
  const [status, setStatus] = useState<Status>("off");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!vapidPublicKey || !("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
      setStatus("unsupported");
      return;
    }
    if (Notification.permission === "denied") {
      setStatus("blocked");
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    setStatus(sub ? "on" : "off");
  }, [vapidPublicKey]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const enable = async () => {
    setError("");
    setStatus("busy");
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus(permission === "denied" ? "blocked" : "off");
        return;
      }
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey) as BufferSource,
      });
      const json = sub.toJSON();
      if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
        throw new Error("O navegador não devolveu a inscrição");
      }
      await api.financePushSubscribe({
        endpoint: json.endpoint,
        keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
      });
      setStatus("on");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível ativar os avisos");
      setStatus("off");
    }
  };

  const disable = async () => {
    setError("");
    setStatus("busy");
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        const json = sub.toJSON();
        if (json.endpoint && json.keys?.p256dh && json.keys?.auth) {
          await api.financePushUnsubscribe({
            endpoint: json.endpoint,
            keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
          });
        }
        await sub.unsubscribe();
      }
      setStatus("off");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível desligar os avisos");
      await refresh();
    }
  };

  if (!vapidPublicKey || status === "unsupported") {
    return (
      <p className="text-xs text-muted">
        Avisos de evento no Android usam o Chrome (de preferência com o app na tela inicial).
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {status === "on" ? (
        <button type="button" className="btn-ghost !py-2 !px-4 text-sm" onClick={() => void disable()}>
          Avisos ligados
        </button>
      ) : (
        <button
          type="button"
          className="btn-ghost !py-2 !px-4 text-sm"
          onClick={() => void enable()}
          disabled={status === "busy" || status === "blocked"}
        >
          {status === "busy" ? "Ativando…" : "Avisar no celular"}
        </button>
      )}
      {status === "blocked" && (
        <span className="text-xs text-muted">Permissão bloqueada nas configurações do Chrome.</span>
      )}
      {status === "on" && (
        <span className="text-xs text-muted">15 min antes do compromisso (Android/Chrome).</span>
      )}
      {error && <span className="text-xs text-[var(--danger)]">{error}</span>}
    </div>
  );
}
