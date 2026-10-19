/* view-concept — the home-screen app's service worker (push.py): it receives the
   server's notices, even while the app is closed, and shows them. It keeps no offline
   copy of the page.

   A notice names a session ({slug, title, body}); it is shown under the session's tag,
   so a session's new notice replaces its previous one, and not at all while that
   session is open and in view in the app. A tap on it opens the session in the app. */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

const sessionUrl = (slug) => new URL(`/s/${encodeURIComponent(slug)}`, self.location.origin).href;

self.addEventListener("push", (e) => {
  let notice = {};
  try { notice = e.data ? e.data.json() : {}; } catch (err) { return; }
  if (!notice.slug) return;
  e.waitUntil((async () => {
    const pages = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (pages.some((c) => c.visibilityState === "visible" && c.url.split(/[?#]/)[0] === sessionUrl(notice.slug))) return;
    await self.registration.showNotification(notice.title || "view-concept", {
      body: notice.body || "",
      tag: notice.slug,
      renotify: true,
      icon: "/static/icon-192.png",
      data: { url: sessionUrl(notice.slug) },
    });
  })());
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil((async () => {
    const pages = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const page = pages[0];
    if (page) {
      await page.focus();
      if (page.url !== url && page.navigate) await page.navigate(url);
      return;
    }
    await self.clients.openWindow(url);
  })());
});
