"""FastAPI server: static web app, /ws event stream, /thermal.mjpg, /api/state. HTTPS on :8443."""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("server")

CLIENT_QUEUE_MAX = 500
MJPEG_PERIOD_S = 0.1   # 10 fps max
MJPEG_RESEND_S = 1.0   # resend the same frame this often so the stream stays alive


class NoCacheStatic(StaticFiles):
    def file_response(self, full_path, *args, **kwargs):
        resp = super().file_response(full_path, *args, **kwargs)
        if str(full_path).endswith((".html", ".js")):
            resp.headers["Cache-Control"] = "no-store"
        return resp


def build_app(bus, cfg) -> FastAPI:
    clients: set[asyncio.Queue] = set()
    state = {"loop": None}

    def fan_out(event):
        # Runs in the bus subscriber thread; hand the event to the asyncio loop.
        loop = state["loop"]
        if loop is not None:
            loop.call_soon_threadsafe(_deliver, event)

    def _deliver(event):
        for q in clients:
            if q.full():
                try:
                    q.get_nowait()  # drop oldest for slow clients
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)

    @asynccontextmanager
    async def lifespan(app):
        state["loop"] = asyncio.get_running_loop()
        bus.subscribe(None, fan_out)
        yield
        state["loop"] = None

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    web_dir = cfg["web_dir"]

    @app.get("/")
    async def root():
        index = os.path.join(web_dir, "index.html")
        if os.path.exists(index):
            return FileResponse(index, headers={"Cache-Control": "no-store"})
        return RedirectResponse("/debug.html")

    @app.get("/api/state")
    async def api_state():
        return JSONResponse(bus.snapshot())

    @app.get("/ca.crt")
    async def ca_cert():
        # Install this on a phone to get rid of the certificate warning for good (see README).
        ca = os.path.join(os.path.dirname(cfg["cert"]), "ca.pem")
        if not os.path.exists(ca):
            return Response("no CA certificate (run ear/tools/make_cert.sh)", status_code=404)
        return FileResponse(ca, media_type="application/x-x509-ca-cert", filename="heimdall-ca.crt")

    @app.get("/thermal.mjpg")
    async def thermal_mjpg():
        async def frames():
            last, last_sent = None, 0.0
            srv = getattr(app.state, "server", None)
            while not (srv and srv.should_exit):
                frame = bus.get_frame()
                now = time.monotonic()
                if frame is not None and (frame is not last or now - last_sent > MJPEG_RESEND_S):
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                    last, last_sent = frame, now
                await asyncio.sleep(MJPEG_PERIOD_S)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=CLIENT_QUEUE_MAX)
        clients.add(q)
        peer = f"{sock.client.host}:{sock.client.port}" if sock.client else "?"
        log.info("ws connect %s (%d clients)", peer, len(clients))

        # Snapshot: every known victim, then the last event of every other type, oldest first.
        snap = bus.snapshot()
        initial = list(snap["victims"].values())
        initial += [e for t, e in snap["last"].items() if t != "victim"]
        initial.sort(key=lambda e: e["ts"] if isinstance(e.get("ts"), (int, float)) else 0.0)

        async def sender():
            for e in initial:
                await sock.send_text(json.dumps(e))
            while True:
                await sock.send_text(json.dumps(await q.get()))

        async def receiver():
            while True:
                text = await sock.receive_text()
                try:
                    msg = json.loads(text)
                except ValueError:
                    log.warning("ws %s sent non-JSON: %.80s", peer, text)
                    continue
                if not isinstance(msg, dict) or not isinstance(msg.get("t"), str):
                    log.warning("ws %s sent message without a string 't': %.80s", peer, text)
                    continue
                msg["ts"] = time.time()      # server clock: the snapshot sorts on ts, so a client's value is never trusted
                bus.publish(msg)

        tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                exc = t.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    log.warning("ws %s closed: %r", peer, exc)
        finally:
            for t in tasks:
                t.cancel()
            clients.discard(q)
            log.info("ws disconnect %s (%d clients)", peer, len(clients))

    app.mount("/", NoCacheStatic(directory=web_dir, html=True), name="web")
    return app


def run(bus, cfg) -> None:
    """Blocking. Serves HTTPS if the cert exists, otherwise plain HTTP with a warning."""
    app = build_app(bus, cfg)
    ssl = {}
    if os.path.exists(cfg["cert"]) and os.path.exists(cfg["key"]):
        ssl = {"ssl_certfile": cfg["cert"], "ssl_keyfile": cfg["key"]}
        scheme = "https"
    else:
        scheme = "http"
        log.warning("NO CERT at %s: serving plain HTTP. Phones will block mic/motion. "
                    "Run ear/tools/make_cert.sh", cfg["cert"])
    log.info("serving %s://%s:%d/  (debug page: /debug.html)", scheme, cfg["host"], cfg["port"])
    srv = uvicorn.Server(uvicorn.Config(app, host=cfg["host"], port=cfg["port"], log_level="warning",
                                        timeout_graceful_shutdown=2, **ssl))
    app.state.server = srv  # lets the MJPEG stream end when Ctrl-C starts shutdown
    srv.run()
