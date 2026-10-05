// Service Worker mínimo para requerimiento PWA (Sprint 0)
self.addEventListener('install', (e) => {
  console.log('[Service Worker] Instalado');
});

self.addEventListener('fetch', (e) => {
  e.respondWith(fetch(e.request));
});