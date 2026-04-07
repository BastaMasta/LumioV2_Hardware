"""
main.py  –  Lumio V2 RP2040 Co-processor Firmware
===================================================
MicroPython firmware for the RP2040 on the Lumio V2 board.

Responsibilities
----------------
* Expose free GPIOs (GP3–GP29, excluding UART pins GP1/GP2) to the
  Raspberry Pi 5 host via a JSON-over-UART protocol.
* Allow the host (and therefore the web UI) to configure each pin as
  digital input, digital output, ADC input, or PWM output at runtime.
* Push async events when a monitored input pin changes state.
* Respond to synchronous host commands within ~5 ms.

UART wiring
-----------
  RP2040 GP1 (TX)  →  RPi5 GPIO15 (RX, ttyAMA0)
  RP2040 GP2 (RX)  ←  RPi5 GPIO14 (TX, ttyAMA0)
  Baud: 115200  8N1

Protocol (newline-delimited JSON)
----------------------------------
Host → RP2040:
  {"cmd": "ping"}
  {"cmd": "gpio_set_mode", "pin": 5, "mode": "input"}   # input|output|adc|pwm|unused
  {"cmd": "gpio_write",    "pin": 5, "value": 1}
  {"cmd": "gpio_read",     "pin": 5}
  {"cmd": "adc_read",      "pin": 26}                    # GP26/27/28/29 have ADC
  {"cmd": "pwm_set",       "pin": 5, "freq": 1000, "duty": 512}  # duty 0-65535
  {"cmd": "list_pins"}
  {"cmd": "get_all"}                                     # snapshot all configured pins

RP2040 → Host (replies):
  {"ok": true}
  {"ok": true, "value": 1}
  {"ok": false, "error": "bad pin"}

RP2040 → Host (async events, pushed on input change):
  {"event": "change", "pin": 5, "value": 1}
"""

import ujson
import utime
import sys
from machine import UART, Pin, ADC, PWM

import protocol
import pin_manager

# ── UART setup (GP1=TX, GP2=RX) ──────────────────────────────────────────────
uart = UART(0, baudrate=115_200, tx=Pin(1), rx=Pin(2), timeout=0)

pm   = pin_manager.PinManager()
proto = protocol.Protocol(uart, pm)

# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    buf = b""
    last_poll = utime.ticks_ms()
    POLL_MS = 20   # check for input-change events every 20 ms

    while True:
        # ── Read incoming bytes ───────────────────────────────────────────────
        chunk = uart.read(256)
        if chunk:
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if line:
                    proto.handle(line)

        # ── Poll monitored inputs for edge events ─────────────────────────────
        now = utime.ticks_ms()
        if utime.ticks_diff(now, last_poll) >= POLL_MS:
            pm.poll_events(proto.push_event)
            last_poll = now

        utime.sleep_ms(1)


main()
