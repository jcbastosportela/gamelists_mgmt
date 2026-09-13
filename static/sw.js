const CACHE_NAME = "rom-manager-v1";

// Install: activate immediately
self.addEventListener("install", (event) => {
    self.skipWaiting();
});

// Activate: claim all clients immediately
self.addEventListener("activate", (event) => {
    event.waitUntil(clients.claim());
});

// Fetch: network-first strategy (app needs live data from the server)
self.addEventListener("fetch", (event) => {
    // Only cache GET requests for static assets
    if (event.request.method !== "GET") return;

    const url = new URL(event.request.url);

    // For API requests and media, always go to network
    if (url.pathname.startsWith("/api/")) {
        return;
    }

    // For static assets, use cache-first
    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) =>
                cache.match(event.request).then((cached) => {
                    const fetchPromise = fetch(event.request).then((response) => {
                        if (response.ok) {
                            cache.put(event.request, response.clone());
                        }
                        return response;
                    });
                    return cached || fetchPromise;
                })
            )
        );
        return;
    }

    // For the main page, use network-first
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
