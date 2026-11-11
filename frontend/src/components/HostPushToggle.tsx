"use client";

import { useCallback, useEffect, useState } from "react";
import { SvgBell } from "@/components/ui/svgs";
import { api } from "@/lib/api";

type Status = "off" | "on" | "blocked" | "unsupported" | "busy" | "missing";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

export function HostPushToggle() {
  const [status, setStatus] = useState<Status>("off");
  const [error, setError] = useState("");
  const [vapidPublicKey, setVapidPublicKey] = useState("");

  const refresh = useCallback(async (key: string) => {
    if (!key || !("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
      setStatus(key ? "unsupported" : "missing");
      return;
    }
    if (Notification.permission === "denied") {
      setStatus("blocked");
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    setStatus(sub ? "on" : "off");
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .hostPushMeta()
      .then((meta) => {
        if (cancelled) return;
        const key = meta.vapid_public_key || "";
        setVapidPublicKey(key);
        void refresh(key);
      })
      .catch(() => {
        if (!cancelled) setStatus("missing");
      });
    return () => {
      cancelled = true;
    };
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
      await api.hostPushSubscribe({
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
        if (json.endpoint) {
          await api.hostPushUnsubscribe({
            endpoint: json.endpoint,
            keys: { p256dh: json.keys?.p256dh || "x".repeat(20), auth: json.keys?.auth || "x".repeat(8) },
          });
        }
        await sub.unsubscribe();
      }
      setStatus("off");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível desligar os avisos");
      await refresh(vapidPublicKey);
    }
  };

  if (status === "missing" || status === "unsupported") {
    return null;
  }

  return (
    <div className="px-4 py-3 border-t border-[var(--glass-border)]">
      <button
        type="button"
        onClick={() => void (status === "on" ? disable() : enable())}
        disabled={status === "busy" || status === "blocked"}
        className="flex items-center gap-3 w-full text-left text-sm text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors disabled:opacity-60"
      >
        <span className="text-[var(--text-muted)]">
          <SvgBell className="w-5 h-5" />
        </span>
        <span>
          {status === "busy"
            ? "Ativando avisos…"
            : status === "on"
              ? "Avisos ligados"
              : status === "blocked"
                ? "Avisos bloqueados"
                : "Ativar avisos no celular"}
        </span>
      </button>
      {status === "on" && (
        <p className="text-xs text-[var(--text-muted)] mt-1 pl-8">
          Pedidos, pagamentos e tickets no Chrome/Android.
        </p>
      )}
      {status === "blocked" && (
        <p className="text-xs text-[var(--text-muted)] mt-1 pl-8">
          Permissão bloqueada nas configurações do Chrome.
        </p>
      )}
      {error && <p className="text-xs text-[var(--danger)] mt-1 pl-8">{error}</p>}
    </div>
  );
}
