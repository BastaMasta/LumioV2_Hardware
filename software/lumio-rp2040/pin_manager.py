"""
pin_manager.py  –  Runtime pin configuration & state tracking
=============================================================
Manages the lifecycle of each GPIO pin: mode, current object,
last-known value (for edge detection), and labels.
"""

from machine import Pin, ADC, PWM
import utime

# ── Constants ─────────────────────────────────────────────────────────────────

# Pins reserved for UART — must never be reconfigured
RESERVED_PINS = {1, 2}

# Pins that have ADC capability on the RP2040
ADC_CAPABLE = {26: 0, 27: 1, 28: 2, 29: 3}   # GP → ADC channel index

# All user-assignable pins (GP3 … GP29, minus reserved)
ASSIGNABLE = [p for p in range(3, 30) if p not in RESERVED_PINS]

MODES = ("input", "output", "adc", "pwm", "unused")


class PinState:
    """Holds everything about one GPIO pin."""
    __slots__ = ("pin_num", "mode", "label", "_obj", "_last_value")

    def __init__(self, pin_num: int):
        self.pin_num    = pin_num
        self.mode       = "unused"
        self.label      = ""
        self._obj       = None
        self._last_value = None

    def release(self):
        """Tear down the current machine object so we can reconfigure."""
        if isinstance(self._obj, PWM):
            self._obj.deinit()
        self._obj = None
        self._last_value = None

    def configure(self, mode: str, label: str = "") -> bool:
        """Apply a new mode. Returns True on success."""
        if mode not in MODES:
            return False
        if self.pin_num in RESERVED_PINS:
            return False
        if mode == "adc" and self.pin_num not in ADC_CAPABLE:
            return False

        self.release()
        self.mode  = mode
        self.label = label

        if mode == "input":
            self._obj = Pin(self.pin_num, Pin.IN, Pin.PULL_DOWN)
            self._last_value = self._obj.value()
        elif mode == "output":
            self._obj = Pin(self.pin_num, Pin.OUT)
            self._obj.value(0)
            self._last_value = 0
        elif mode == "adc":
            self._obj = ADC(ADC_CAPABLE[self.pin_num])
            self._last_value = None
        elif mode == "pwm":
            self._obj = PWM(Pin(self.pin_num))
            self._obj.freq(1000)
            self._obj.duty_u16(0)
            self._last_value = 0
        # "unused" → _obj stays None

        return True

    # ── Read helpers ──────────────────────────────────────────────────────────

    def digital_read(self):
        if self.mode in ("input", "output") and self._obj:
            return self._obj.value()
        return None

    def adc_read_u16(self):
        """Raw 16-bit ADC reading (0-65535)."""
        if self.mode == "adc" and self._obj:
            return self._obj.read_u16()
        return None

    def adc_read_voltage(self):
        """Voltage in volts (3.3 V reference)."""
        raw = self.adc_read_u16()
        if raw is None:
            return None
        return round(raw * 3.3 / 65535, 4)

    # ── Write helpers ─────────────────────────────────────────────────────────

    def digital_write(self, value: int) -> bool:
        if self.mode == "output" and self._obj:
            self._obj.value(int(bool(value)))
            self._last_value = int(bool(value))
            return True
        return False

    def pwm_set(self, freq: int, duty: int) -> bool:
        """duty: 0-65535 (u16)."""
        if self.mode == "pwm" and self._obj:
            self._obj.freq(max(1, freq))
            self._obj.duty_u16(max(0, min(65535, duty)))
            return True
        return False

    # ── Edge detection ────────────────────────────────────────────────────────

    def check_edge(self):
        """
        Returns (True, new_value) if the pin value changed since last check,
        (False, None) otherwise.  Only meaningful for input pins.
        """
        if self.mode != "input" or self._obj is None:
            return False, None
        v = self._obj.value()
        if v != self._last_value:
            self._last_value = v
            return True, v
        return False, None

    def to_dict(self):
        v = self.digital_read()
        if v is None:
            v = self.adc_read_voltage()
        return {
            "pin":   self.pin_num,
            "mode":  self.mode,
            "label": self.label,
            "value": v,
        }


# ── PinManager ────────────────────────────────────────────────────────────────

class PinManager:
    def __init__(self):
        self._pins = {p: PinState(p) for p in ASSIGNABLE}

    def _get(self, pin: int) -> PinState | None:
        return self._pins.get(pin)

    # ── Public API called by Protocol ─────────────────────────────────────────

    def set_mode(self, pin: int, mode: str, label: str = "") -> tuple[bool, str]:
        ps = self._get(pin)
        if ps is None:
            return False, f"pin {pin} not assignable"
        if pin in RESERVED_PINS:
            return False, "reserved pin"
        ok = ps.configure(mode, label)
        if not ok:
            return False, f"cannot set pin {pin} to mode '{mode}'"
        return True, ""

    def gpio_read(self, pin: int) -> tuple[bool, int | None, str]:
        ps = self._get(pin)
        if ps is None:
            return False, None, "invalid pin"
        v = ps.digital_read()
        if v is None:
            return False, None, f"pin {pin} is not a digital input/output (mode={ps.mode})"
        return True, v, ""

    def gpio_write(self, pin: int, value: int) -> tuple[bool, str]:
        ps = self._get(pin)
        if ps is None:
            return False, "invalid pin"
        if not ps.digital_write(value):
            return False, f"pin {pin} not in output mode"
        return True, ""

    def adc_read(self, pin: int) -> tuple[bool, float | None, str]:
        ps = self._get(pin)
        if ps is None:
            return False, None, "invalid pin"
        v = ps.adc_read_voltage()
        if v is None:
            return False, None, f"pin {pin} not in adc mode"
        return True, v, ""

    def pwm_set(self, pin: int, freq: int, duty: int) -> tuple[bool, str]:
        ps = self._get(pin)
        if ps is None:
            return False, "invalid pin"
        if not ps.pwm_set(freq, duty):
            return False, f"pin {pin} not in pwm mode"
        return True, ""

    def list_pins(self) -> list:
        return [ps.to_dict() for ps in self._pins.values()]

    def get_all(self) -> list:
        """Snapshot of all configured (non-unused) pins."""
        return [ps.to_dict() for ps in self._pins.values() if ps.mode != "unused"]

    def poll_events(self, callback):
        """
        Called every POLL_MS ms from main loop.
        callback(pin, value) is invoked for each edge detected on input pins.
        """
        for ps in self._pins.values():
            changed, val = ps.check_edge()
            if changed:
                callback(ps.pin_num, val)
