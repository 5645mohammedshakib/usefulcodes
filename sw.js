const CACHE='student-hub-v13';
const STATIC=['./student.html','./index.html','./icon-192.png','./icon-512.png','./student-manifest.json','./admin-manifest.json'];

self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));
  return self.clients.claim();
});

self.addEventListener('fetch',e=>{
  if (e.request.method !== 'GET' || e.request.url.includes('onrender.com') || e.request.url.includes('/api/')) {
    return;
  }
  
  // Check if requesting HTML file
  const url = e.request.url;
  const isHtml = url.endsWith('.html') || url.endsWith('/') || (!url.split('/').pop().includes('.'));
  
  if (isHtml) {
    // Network-First: Always try to get latest HTML from network first
    e.respondWith(
      fetch(e.request).then(res=>{
        if(res && res.status===200 && res.type==='basic') {
          const clone=res.clone();
          caches.open(CACHE).then(c=>c.put(e.request,clone));
        }
        return res;
      }).catch(()=>{
        return caches.match(e.request);
      })
    );
  } else {
    // Cache-First: Use cached static assets (images, css, etc.)
    e.respondWith(
      caches.match(e.request).then(cached=>{
        if (cached) return cached;
        return fetch(e.request).then(res=>{
          if(res && res.status===200 && res.type==='basic') {
            const clone=res.clone();
            caches.open(CACHE).then(c=>c.put(e.request,clone));
          }
          return res;
        });
      })
    );
  }
});
