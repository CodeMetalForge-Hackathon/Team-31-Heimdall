"""Ear entry point:  python -m ear.main   (modules from config, or HEIMDALL_MODULES=mock,thermal)."""
import importlib
import logging
import pkgutil
import signal
import threading
import time

from ear import modules as modules_pkg
from ear import server
from ear.bus import Bus
from ear.config import CONFIG

log = logging.getLogger("main")


class Supervisor:
    """Runs each module's run(bus, cfg) in a daemon thread and restarts it after a crash."""

    def __init__(self, bus, cfg):
        self.bus = bus
        self.cfg = cfg
        self.status = {}
        self.lock = threading.Lock()
        available = {m.name for m in pkgutil.iter_modules(modules_pkg.__path__)}
        for name in sorted(available - set(cfg["modules"])):
            self.status[name] = "off"

    def set_status(self, name, value):
        with self.lock:
            changed = self.status.get(name) != value
            self.status[name] = value
        if changed:
            self.publish_health()

    def publish_health(self):
        with self.lock:
            mods = dict(self.status)
        self.bus.publish({"t": "health", "modules": mods})

    def start(self):
        for name in self.cfg["modules"]:
            self.status[name] = "ok"
            threading.Thread(target=self._supervise, args=(name,), daemon=True, name=f"mod-{name}").start()
        threading.Thread(target=self._health_loop, daemon=True, name="health").start()

    def _supervise(self, name):
        full = f"ear.modules.{name}"
        while True:
            try:
                mod = importlib.import_module(full)
            except ModuleNotFoundError as e:
                if e.name == full:
                    log.error("module %s not found (ear/modules/%s.py)", name, name)
                    self.set_status(name, "error")
                    return
                log.exception("module %s failed to import", name)
                self.set_status(name, "error")
                time.sleep(self.cfg["restart_delay_s"])
                continue
            except Exception:
                log.exception("module %s failed to import", name)
                self.set_status(name, "error")
                time.sleep(self.cfg["restart_delay_s"])
                continue

            self.set_status(name, "ok")
            log.info("module %s started", name)
            try:
                mod.run(self.bus, self.cfg.get(name, {}))
                # A clean return means "nothing to do here" (e.g. no device): stay off, don't restart.
                log.warning("module %s returned; marking off", name)
                self.set_status(name, "off")
                return
            except Exception:
                log.exception("module %s crashed; restarting in %.0f s", name, self.cfg["restart_delay_s"])
                self.set_status(name, "error")
                time.sleep(self.cfg["restart_delay_s"])

    def _health_loop(self):
        while True:
            self.publish_health()
            time.sleep(self.cfg["health_period_s"])


def _stop(signum, frame):
    # systemctl stop and restart_ear.sh send SIGTERM. Treat it like Ctrl-C so Python exits normally
    # and the exit hooks run (pantilt points the head straight ahead).
    raise KeyboardInterrupt


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    log.info("Heimdall Ear starting, modules: %s", ", ".join(CONFIG["modules"]) or "(none)")
    signal.signal(signal.SIGTERM, _stop)
    bus = Bus()
    Supervisor(bus, CONFIG).start()
    try:
        server.run(bus, CONFIG)  # blocks; uvicorn handles Ctrl-C
    except KeyboardInterrupt:
        pass
    log.info("bye")


if __name__ == "__main__":
    main()
