"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { API_URL } from "@/lib/apiBase";

const VISITOR_KEY = "ch_vid";
const SESSION_KEY = "ch_sid";
const MAX_BATCH = 20;
const FLUSH_MS = 4000;
const SECRET_QUERY = /^(token|ticket|code|pix|password|secret|brcode|qr|access_token|session|key|otp)$/i;

type Pending = {
  name: "page_view" | "click" | "form_submit" | "page_leave";
  path: string;
  label?: string;
  target?: string;
  href?: string;
  visitor_id: string;
  session_id: string;
  referrer: string;
  language: string;
  timezone: string;
  ua: string;
  viewport_w: number;
  viewport_h: number;
  duration_ms?: number;
  scroll_pct?: number;
};

let queue: Pending[] = [];
let flushTimer: number | null = null;
let pageStarted = 0;
let lastPath = "";
let maxScroll = 0;

function rid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  let hex = "";
  for (let i = 0; i < bytes.length; i += 1) {
    hex += bytes[i].toString(16).padStart(2, "0");
  }
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function readId(storage: Storage, key: string): string {
  try {
    const current = storage.getItem(key);
    if (current && current.length >= 8) return current;
    const next = rid();
    storage.setItem(key, next);
    return next;
  } catch {
    return rid();
  }
}

function sanitizePath(raw: string): string {
  try {
    const url = new URL(raw, window.location.origin);
    const kept: string[] = [];
    url.searchParams.forEach((value, key) => {
      if (SECRET_QUERY.test(key)) return;
      if (key === "tab" || key === "days") kept.push(`${key}=${value.slice(0, 24)}`);
    });
    const path = (url.pathname || "/").slice(0, 200);
    return kept.length ? `${path}?${kept.sort().join("&")}` : path;
  } catch {
    return "/";
  }
}

function context(): Pick<
  Pending,
  "visitor_id" | "session_id" | "referrer" | "language" | "timezone" | "ua" | "viewport_w" | "viewport_h"
> {
  return {
    visitor_id: readId(window.localStorage, VISITOR_KEY),
    session_id: readId(window.sessionStorage, SESSION_KEY),
    referrer: document.referrer || "",
    language: navigator.language || "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
    ua: navigator.userAgent || "",
    viewport_w: window.innerWidth || 0,
    viewport_h: window.innerHeight || 0,
  };
}

function currentPath(): string {
  return sanitizePath(`${window.location.pathname}${window.location.search}`);
}

function enqueue(event: Omit<Pending, keyof ReturnType<typeof context>> & Partial<Pending>) {
  const next: Pending = {
    ...context(),
    path: event.path || currentPath(),
    name: event.name!,
    label: (event.label || "").slice(0, 80),
    target: (event.target || "").slice(0, 80),
    href: event.href ? sanitizePath(event.href) : "",
    duration_ms: event.duration_ms || 0,
    scroll_pct: event.scroll_pct || 0,
  };
  queue.push(next);
  if (queue.length >= MAX_BATCH) {
    void flush(false);
    return;
  }
  if (flushTimer == null) {
    flushTimer = window.setTimeout(() => {
      flushTimer = null;
      void flush(false);
    }, FLUSH_MS);
  }
}

async function flush(keepalive: boolean) {
  if (!queue.length) return;
  const events = queue.slice(0, MAX_BATCH);
  queue = queue.slice(events.length);
  try {
    await fetch(`${API_URL}/api/analytics/collect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      keepalive,
      body: JSON.stringify({ events }),
    });
  } catch {
    queue = events.concat(queue).slice(0, 80);
  }
}

function scrollPct(): number {
  const doc = document.documentElement;
  const total = doc.scrollHeight - window.innerHeight;
  if (total <= 0) return 100;
  return Math.max(0, Math.min(100, Math.round((window.scrollY / total) * 100)));
}

function trackLeave() {
  if (!lastPath) return;
  enqueue({
    name: "page_leave",
    path: lastPath,
    duration_ms: Math.max(0, Date.now() - pageStarted),
    scroll_pct: Math.max(maxScroll, scrollPct()),
  });
}

function clickTarget(node: EventTarget | null): HTMLElement | null {
  if (!(node instanceof Element)) return null;
  return node.closest("button, a, [role='button'], input[type='submit'], summary") as HTMLElement | null;
}

function labelFor(el: HTMLElement): string {
  const tracked = el.getAttribute("data-track") || el.closest("[data-track]")?.getAttribute("data-track");
  if (tracked) return tracked.slice(0, 80);
  const aria = el.getAttribute("aria-label");
  if (aria) return aria.slice(0, 80);
  const text = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
  return text.slice(0, 80);
}

export function AnalyticsTracker() {
  const pathname = usePathname();

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const el = clickTarget(event.target);
      if (!el) return;
      if (el.closest("[data-analytics='off']")) return;
      const href = el instanceof HTMLAnchorElement ? el.getAttribute("href") || "" : "";
      enqueue({
        name: "click",
        path: currentPath(),
        label: labelFor(el),
        target: `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ""}`,
        href,
      });
    };
    const onSubmit = (event: Event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      enqueue({
        name: "form_submit",
        path: currentPath(),
        label: form.getAttribute("name") || form.id || form.getAttribute("aria-label") || "form",
        target: form.getAttribute("action") || "",
      });
    };
    const onScroll = () => {
      maxScroll = Math.max(maxScroll, scrollPct());
    };
    const onHide = () => {
      trackLeave();
      void flush(true);
    };

    document.addEventListener("click", onClick, true);
    document.addEventListener("submit", onSubmit, true);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", onHide);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") onHide();
    });

    return () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("submit", onSubmit, true);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", onHide);
    };
  }, []);

  useEffect(() => {
    if (lastPath && lastPath !== currentPath()) {
      trackLeave();
    }
    pageStarted = Date.now();
    maxScroll = 0;
    lastPath = currentPath();
    enqueue({ name: "page_view", path: lastPath });
  }, [pathname]);

  return null;
}
