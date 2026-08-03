/* AdminFut Service Worker - Web Push (PWA) */
var CACHE = 'adminfut-v1';

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(['/']);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE; })
            .map(function (k) { return caches.delete(k); })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then(function (response) {
        var copy = response.clone();
        caches.open(CACHE).then(function (cache) { cache.put(req, copy); });
        return response;
      }).catch(function () {
        return caches.match(req).then(function (hit) { return hit || caches.match('/'); });
      })
    );
    return;
  }
  event.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req);
    })
  );
});

self.addEventListener('push', function (event) {
  var payload = null;
  try {
    payload = event.data.json();
  } catch (e) {
    payload = {
      title: 'AdminFut',
      body: event.data ? event.data.text() : '',
      data: {}
    };
  }
  var title = payload.title || 'AdminFut';
  var options = {
    body: payload.body || '',
    icon: '/pwa-icon/icon-192.png',
    badge: '/pwa-icon/badge-96.png',
    data: payload.data || {},
    vibrate: [100, 50, 100]
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if ('focus' in list[i]) { list[i].focus(); return; }
      }
      if (self.clients.openWindow) { return self.clients.openWindow(url); }
    })
  );
});
