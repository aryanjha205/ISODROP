const CACHE_NAME = 'isodrop-v6';
const ASSETS = [
    '/',
    '/manifest.json',
    '/static/icon.png',
    '/static/css/style.css',
    '/static/js/app.js'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request).then((response) => {
            return response || fetch(event.request);
        })
    );
});
