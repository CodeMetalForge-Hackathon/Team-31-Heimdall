/* HEIMDALL operator page, live mode: station WebSocket -> HeimdallOperator hooks.
 * Reconnects with backoff (0.5, 1, 2, 5 s), treats 12 s of silence as a dead socket
 * (the station sends health every 5 s), and recovers right away when an iPhone comes
 * back from the background. Commands typed while offline: the latest of each type is
 * sent after reconnecting.
 */
(function () {
  'use strict';

  const op = window.HeimdallOperator;
  if (!op) { console.error('[HEIMDALL] operator-live.js: HeimdallOperator missing'); return; }

  const BACKOFF_S = [0.5, 1, 2, 5];
  const WATCHDOG_S = 12;
  const URL_WS = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
  const THERMAL = '/thermal.mjpg';

  let sock = null;
  let attempt = 0;          // failed connects in a row, picks the backoff
  let opens = 0;            // sockets opened so far: from the second one on, the MJPEG stream is restarted too
  let openedAt = 0;         // when the current socket opened; only a socket that held 5 s earns a fresh backoff
  let retryTimer = null;
  let lastMsgAt = 0;
  const pending = new Map(); // command type -> {cmd, seq}, sent after reconnect
  let seq = 0;

  function log(...a) { console.log('[HEIMDALL ws]', ...a); }

  function connect() {
    clearTimeout(retryTimer);
    retryTimer = null;
    if (sock && (sock.readyState === WebSocket.OPEN || sock.readyState === WebSocket.CONNECTING)) return;
    op.setConnection('connecting');
    let s;
    try { s = new WebSocket(URL_WS); } catch (e) { log('connect failed', e); scheduleRetry(); return; }
    sock = s;
    s.onopen = () => {
      if (s !== sock) return;
      log('open');
      lastMsgAt = openedAt = Date.now();
      op.setConnection('live');
      if (opens++ > 0) op.setThermalSource(THERMAL + '?t=' + Date.now());   // the old MJPEG stream died with the link
      flushPending();
    };
    s.onmessage = (m) => {
      if (s !== sock) return;
      lastMsgAt = Date.now();
      if (Date.now() - openedAt > 5000) attempt = 0; // held for 5 s: the next drop starts the backoff from 0.5 s again
      // (not on the snapshot burst alone: a server that accepts and closes at once would otherwise get a connect every 0.6 s)
      let evt;
      try { evt = JSON.parse(m.data); } catch (e) { return; }
      op.handleEvent(evt);
    };
    s.onclose = s.onerror = () => {
      if (s !== sock) return;
      sock = null;
      try { s.close(); } catch (e) { /* already closed */ }
      op.setConnection('lost');
      scheduleRetry();
    };
  }

  function scheduleRetry() {
    if (retryTimer) return;
    const d = BACKOFF_S[Math.min(attempt, BACKOFF_S.length - 1)];
    attempt++;
    retryTimer = setTimeout(connect, d * 1000);
  }

  function drop(reason) {
    log('dropping socket:', reason);
    const s = sock;
    sock = null;
    if (s) { s.onopen = s.onmessage = s.onclose = s.onerror = null; try { s.close(); } catch (e) { /* ignore */ } }
    op.setConnection('lost');
  }

  // A socket can sit "open" after Wi-Fi drops or the phone sleeps; health arrives every 5 s.
  setInterval(() => {
    if (sock && sock.readyState === WebSocket.OPEN && Date.now() - lastMsgAt > WATCHDOG_S * 1000) {
      drop('no message for ' + WATCHDOG_S + ' s');
      scheduleRetry();
    }
  }, 1000);

  function send(cmd) {
    if (sock && sock.readyState === WebSocket.OPEN) {
      try { sock.send(JSON.stringify(cmd)); return true; } catch (e) { log('send failed', e); }
    }
    return false;
  }

  function flushPending() {
    const list = [...pending.values()].sort((a, b) => a.seq - b.seq);
    pending.clear();
    for (const p of list) {
      if (!send(p.cmd)) { pending.set(p.cmd.t, p); }
    }
  }

  op.onCommand((cmd) => {
    if (!cmd || !cmd.t) return;
    if (send(cmd)) return;
    if (cmd.t === 'pantilt_cmd' || cmd.t === 'pantilt_mode') pending.set(cmd.t, { cmd, seq: seq++ });
  });

  // iPhone Safari kills the socket in the background and the MJPEG <img> freezes.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    op.setThermalSource(THERMAL + '?t=' + Date.now());
    const stale = Date.now() - lastMsgAt > 6000;
    if (!sock || sock.readyState !== WebSocket.OPEN || stale) {
      if (sock) drop('back from background');
      attempt = 0;
      connect();
    }
  });
  window.addEventListener('pageshow', (e) => { if (e.persisted) { attempt = 0; drop('restored from bfcache'); connect(); } });
  window.addEventListener('online', () => { if (!sock) { attempt = 0; connect(); } });

  op.setConnection('connecting');
  op.setThermalSource(THERMAL);
  connect();
})();
