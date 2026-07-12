const CACHE_NAME = 'apacuana-cache-v1';

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', event => {
  // Pass-through fetch for now, just to satisfy PWA installability requirements
  // In a production scenario with complex auth, it's better to rely on network first.
  if (event.request.method !== 'GET') return;
  
  event.respondWith(
    fetch(event.request).catch(error => {
      return caches.match(event.request);
    })
  );
});
