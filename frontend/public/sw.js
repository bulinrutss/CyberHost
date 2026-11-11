/* CyberHost PWA: pass-through + avisos de pedidos, pagamentos e tickets. */
self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  const title = data.title || "CyberHost";
  const options = {
    body: data.body || "Você tem um aviso no painel",
    icon: "pwa-icon-192.png",
    badge: "pwa-icon-192.png",
    tag: data.tag || "cyberhost",
    data: { url: data.url || "/dashboard" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const raw = (event.notification.data && event.notification.data.url) || "/dashboard";
  const target = new URL(String(raw).replace(/^\//, ""), self.registration.scope).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (client.url.startsWith(self.registration.scope) && "focus" in client) {
          client.focus();
          if (client.url !== target && "navigate" in client) {
            return client.navigate(target);
          }
          return client;
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(target);
      }
      return undefined;
    })
  );
});
