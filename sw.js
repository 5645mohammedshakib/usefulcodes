const CACHE='student-hub-v3';
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
  // Never cache API calls - always go to network
  if(e.request.url.includes('onrender.com')||e.request.url.includes('/api/')){
    e.respondWith(fetch(e.request));
    return;
  }
  // For static files: cache first, network fallback
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));
});
