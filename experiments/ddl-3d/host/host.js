'use strict';
// The parent page of the viewer frame for the native apps (Web `Ddl3DHost.svelte`'s
// iframe and listener). The viewer checks that its parent is a same-origin window
// (src/main.ts), so a native app serves this page and the registered viewer build
// under one origin and loads this page with `?mount=<id>&viewer=<viewerUrl>&title=<t>`.
//
// It checks the origin, the frame's window, the mount identity and the protocol,
// asks for the viewer's ready state when mounted and again after the frame loads,
// and relays both ways. Request numbers, the 15-second deadline and stale results
// are the native controller's.
//
// The way to the app is the only native difference:
// - Apple (WKWebView): `webkit.messageHandlers.ddl3d` out; the app calls
//   `window.inku3d.deliver(message)` and `window.inku3d.focus()` in.
// - Android (WebView): the app hands the main frame one end of a MessageChannel
//   (`postWebMessage`, data `inku.ddl3d.native`); JSON text goes both ways on it,
//   `{kind: 'deliver', message}`, `{kind: 'focus'}` and `{kind: 'download', url, name}` in.
(() => {
  const PROTOCOL = 'inku.ddl3d.v1';
  const NATIVE_PORT = 'inku.ddl3d.native';
  const query = new URLSearchParams(location.search);
  const mountId = query.get('mount') || '';
  const viewer = query.get('viewer') || '';
  const apple = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.ddl3d;
  let port = null;
  const waiting = [];
  let frame = null;
  const tell = message => {
    if (apple) apple.postMessage(message);
    else if (port) port.postMessage(JSON.stringify(message));
    else waiting.push(message);
  };
  const fail = reason => tell({ type: 'host-failed', mountId, reason });
  const hex64 = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
  const count = value => Number.isSafeInteger(value) && value >= 0 ? value : -1;
  // Web protocol.ts validViewState.
  const vector = a => Array.isArray(a) && a.length === 3 && a.every(n => Number.isFinite(n) && Math.abs(n) < 10000);
  const validViewState = v => !!v && typeof v === 'object' && vector(v.position) && vector(v.target)
    && Number.isFinite(v.zoom) && v.zoom >= 0.001 && v.zoom <= 1000
    && (v.projection === 'perspective' || v.projection === 'orthographic') && v.depth >= 0.1 && v.depth <= 3
    && (v.layerSpacing === undefined || (Number.isFinite(v.layerSpacing) && v.layerSpacing >= 0 && v.layerSpacing <= 3))
    && (v.background === undefined || ['none', 'support', 'sky', 'stars', 'paint', 'white', 'black'].includes(v.background))
    && (v.referenceHeight === undefined || (Number.isFinite(v.referenceHeight) && v.referenceHeight > 0 && v.referenceHeight < 1000))
    && (v.displayZoom === undefined || (Number.isFinite(v.displayZoom) && v.displayZoom > 0 && v.displayZoom <= 10000))
    && Number.isFinite(v.orthoHeight) && v.orthoHeight > 0 && v.orthoHeight < 1000;
  function deliver(message) {
    if (!frame || !frame.contentWindow) return;
    try { frame.contentWindow.postMessage(message, location.origin); }
    catch (error) { fail('post_failed:' + ((error && error.name) || 'error')); }
  }
  function focus() { if (frame) frame.focus(); }
  // A PNG or GLB the viewer saved, read from its same-origin blob URL while it
  // lives (the viewer revokes it after a second) and handed to the app.
  function download(url, name) {
    if (typeof url !== 'string' || !url.startsWith('blob:' + location.origin + '/')) return;
    fetch(url).then(response => response.blob()).then(blob => new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({ type: blob.type, data: String(reader.result) });
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    })).then(file => tell({ type: 'download', mountId, name: String(name || ''), mimeType: file.type, dataUrl: file.data }))
      .catch(error => tell({ type: 'download-failed', mountId, reason: (error && error.name) || 'error' }));
  }
  window.addEventListener('message', event => {
    // Android's channel: once, from the app (no source window), before anything else.
    if (!apple && !port && event.source === null && event.data === NATIVE_PORT && event.ports && event.ports.length === 1) {
      port = event.ports[0];
      port.onmessage = message => {
        let data;
        try { data = JSON.parse(message.data); } catch (_) { return; }
        if (!data || typeof data !== 'object') return;
        if (data.kind === 'deliver' && data.message && typeof data.message === 'object') deliver(data.message);
        else if (data.kind === 'focus') focus();
        else if (data.kind === 'download') download(data.url, data.name);
      };
      waiting.splice(0).forEach(tell);
      return;
    }
    if (!frame || event.origin !== location.origin || event.source !== frame.contentWindow) return;
    const data = event.data;
    if (!data || typeof data !== 'object' || data.mountId !== mountId) return;
    if (data.protocol !== PROTOCOL) { tell({ type: 'protocol-mismatch', mountId }); return; }
    const requestId = Number.isSafeInteger(data.requestId) ? data.requestId : -1;
    if (data.type === 'ready') tell({ type: 'ready', mountId, requestId });
    else if (data.type === 'rendered' && hex64(data.inputDigest)) {
      tell({ type: 'rendered', mountId, requestId, inputDigest: data.inputDigest, objectCount: count(data.objectCount),
             triangles: count(data.triangles), bytes: count(data.bytes), preparationMs: count(data.preparationMs) });
    } else if (data.type === 'failed' && typeof data.reason === 'string') {
      tell({ type: 'failed', mountId, requestId, reason: data.reason.slice(0, 500) });
    } else if (data.type === 'view-state' && validViewState(data.viewState)) {
      tell({ type: 'view-state', mountId, requestId, viewState: JSON.stringify(data.viewState) });
    } else if (data.type === 'return-2d') tell({ type: 'return-2d', mountId, requestId });
  });
  const requestReady = () => deliver({ protocol: PROTOCOL, type: 'request-ready', mountId, requestId: 0 });
  window.inku3d = { deliver, focus, download };
  if (!/^[A-Za-z0-9._-]{1,128}$/.test(mountId)
      || !/^\/experimental\/ddl-3d\/[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}\/index\.html$/.test(viewer)) { fail('invalid_mount'); return; }
  frame = document.createElement('iframe');
  frame.title = query.get('title') || '3D';
  frame.allow = 'fullscreen';
  frame.allowFullscreen = true;
  frame.referrerPolicy = 'no-referrer';
  frame.addEventListener('load', requestReady);
  document.body.append(frame);
  // Navigate after attachment: a src set on a detached frame can leave it at about:blank (Web Ddl3DHost).
  frame.src = viewer + '#mount=' + encodeURIComponent(mountId);
  requestReady();
})();
