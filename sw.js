const CACHE='student-hub-v4';
const STATIC=['./student.html','./index.html','./icon-192.png','./icon-512.png'];

self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));
  return self.clients.claim();
});

self.addEventListener('fetch',e=>{
  // Only handle GET requests for static assets.
  // Never intercept POST/PUT/DELETE or API calls!
  if (e.request.method !== 'GET' || e.request.url.includes('onrender.com') || e.request.url.includes('/api/')) {
    return; // Let the browser handle it naturally from network
  }
  
  e.respondWith(
    caches.match(e.request).then(cachedResponse => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(e.request);
    })
  );
});
