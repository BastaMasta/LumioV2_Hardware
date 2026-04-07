"""
protocol.py  –  JSON UART command dispatcher
============================================
Parses incoming newline-delimited JSON frames from the RPi5,
dispatches to PinManager, and writes back JSON replies.
Also provides push_event() for async input-change notifications.
"""

import ujson


class Protocol:
    def __init__(self, uart, pin_manager):
        self._uart = uart
        self._pm   = pin_manager

    # ── Low-level send ────────────────────────────────────────────────────────

    def _send(self, obj: dict):
        line = ujson.dumps(obj) + "\n"
        self._uart.write(line.encode())

    def _ok(self, **extra):
        self._send({"ok": True, **extra})

    def _err(self, msg: str):
        self._send({"ok": False, "error": msg})

    # ── Async event push ──────────────────────────────────────────────────────

    def push_event(self, pin: int, value: int):
        """Called by PinManager.poll_events() on input edge."""
        self._send({"event": "change", "pin": pin, "value": value})

    # ── Command dispatcher ────────────────────────────────────────────────────

    def handle(self, raw: bytes):
        try:
            frame = ujson.loads(raw)
        except Exception:
            self._err("json parse error")
            return

        cmd = frame.get("cmd", "")

        if cmd == "ping":
            self._ok()

        elif cmd == "gpio_set_mode":
            pin   = frame.get("pin")
            mode  = frame.get("mode", "input")
            label = frame.get("label", "")
            if pin is None:
                self._err("missing pin")
                return
            ok, msg = self._pm.set_mode(int(pin), mode, label)
            if ok:
                self._ok()
            else:
                self._err(msg)

        elif cmd == "gpio_write":
            pin   = frame.get("pin")
            value = frame.get("value", 0)
            if pin is None:
                self._err("missing pin")
                return
            ok, msg = self._pm.gpio_write(int(pin), int(value))
            if ok:
                self._ok()
            else:
                self._err(msg)

        elif cmd == "gpio_read":
            pin = frame.get("pin")
            if pin is None:
                self._err("missing pin")
                return
            ok, val, msg = self._pm.gpio_read(int(pin))
            if ok:
                self._ok(value=val)
            else:
                self._err(msg)

        elif cmd == "adc_read":
            pin = frame.get("pin")
            if pin is None:
                self._err("missing pin")
                return
            ok, val, msg = self._pm.adc_read(int(pin))
            if ok:
                self._ok(value=val)
            else:
                self._err(msg)

        elif cmd == "pwm_set":
            pin  = frame.get("pin")
            freq = int(frame.get("freq", 1000))
            duty = int(frame.get("duty", 0))
            if pin is None:
                self._err("missing pin")
                return
            ok, msg = self._pm.pwm_set(int(pin), freq, duty)
            if ok:
                self._ok()
            else:
                self._err(msg)

        elif cmd == "list_pins":
            pins = self._pm.list_pins()
            self._send({"ok": True, "pins": pins})

        elif cmd == "get_all":
            pins = self._pm.get_all()
            self._send({"ok": True, "pins": pins})

        else:
            self._err(f"unknown cmd: {cmd}")
