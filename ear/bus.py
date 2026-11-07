"""In-process publish/subscribe bus. Every Ear module talks through this."""
import json
import logging
import queue
import threading
import time

log = logging.getLogger("bus")

QUEUE_MAX = 200


class _Subscriber:
    """One worker thread per subscriber, bounded queue, drop oldest when full."""

    def __init__(self, topic, fn):
        self.topic = topic
        self.fn = fn
        self.q = queue.Queue(maxsize=QUEUE_MAX)
        self.thread = threading.Thread(target=self._loop, daemon=True,
                                       name=f"sub-{topic or '*'}-{getattr(fn, '__name__', 'fn')}")
        self.thread.start()

    def put(self, event):
        while True:
            try:
                self.q.put_nowait(event)
                return
            except queue.Full:
                try:
                    self.q.get_nowait()  # drop oldest
                except queue.Empty:
                    pass

    def _loop(self):
        while True:
            event = self.q.get()
            try:
                self.fn(event)
            except Exception:
                log.exception("subscriber %s failed on %s", self.thread.name, event.get("t"))


class Bus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subs = []
        self._victims = {}
        self._last = {}
        self._frame = None

    def publish(self, event: dict) -> None:
        if "t" not in event:
            raise ValueError("event needs a 't' field")
        event.setdefault("ts", time.time())
        with self._lock:
            self._last[event["t"]] = event
            if event["t"] == "victim" and event.get("id"):
                self._victims[event["id"]] = event
            subs = list(self._subs)
        for s in subs:
            if s.topic is None or s.topic == event["t"]:
                s.put(event)

    def subscribe(self, topic, fn) -> None:
        """topic: event type string, or None for all events. fn(event) runs in its own thread."""
        sub = _Subscriber(topic, fn)
        with self._lock:
            self._subs.append(sub)

    def set_frame(self, jpeg: bytes) -> None:
        self._frame = jpeg

    def get_frame(self) -> bytes | None:
        return self._frame

    def snapshot(self) -> dict:
        with self._lock:
            return {"victims": dict(self._victims), "last": dict(self._last)}


class PrintBus(Bus):
    """Bus that also prints every event as one JSON line. For standalone module tests."""

    def publish(self, event: dict) -> None:
        super().publish(event)
        print(json.dumps(event), flush=True)
