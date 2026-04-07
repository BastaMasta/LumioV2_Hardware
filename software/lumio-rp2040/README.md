# Lumio V2 – RP2040 Co-processor Firmware

MicroPython firmware for the RP2040 on the Lumio V2 board.

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry point – UART read loop + event polling |
| `pin_manager.py` | Runtime pin configuration & edge detection |
| `protocol.py` | JSON command parser & reply serialiser |

---

## Flashing (first time)

### 1. Install MicroPython on the RP2040

1. Hold **BOOTSEL** button on the RP2040 while plugging USB into your PC
2. It mounts as a USB drive called `RPI-RP2`
3. Download the latest MicroPython UF2 from https://micropython.org/download/RPI_PICO/
4. Drag the `.uf2` file onto the `RPI-RP2` drive
5. The RP2040 reboots into MicroPython automatically

### 2. Copy firmware files

Use **mpremote** (install with `pip install mpremote`):

```bash
# From the lumio-rp2040/ directory
mpremote connect auto cp main.py pin_manager.py protocol.py :
```

Or use **Thonny IDE** → connect to RP2040 → save each file to the device.

### 3. Verify

```bash
mpremote connect auto repl
# You should see the REPL. main.py runs automatically on power-up.
# Press Ctrl-C to interrupt if needed.
```

---

## UART Wiring

| RP2040 | RPi5 BCM GPIO | Signal |
|---|---|---|
| GP1 (TX) | GPIO 15 (RX) | Data to RPi |
| GP2 (RX) | GPIO 14 (TX) | Data from RPi |
| GND | GND | Common ground |

Baud: **115200**, 8N1, no flow control.

---

## Protocol Reference

All messages are newline-terminated JSON (`\n`).

### Host → RP2040 (commands)

```jsonc
// Health check
{"cmd": "ping"}

// Configure a pin
{"cmd": "gpio_set_mode", "pin": 5, "mode": "input",  "label": "IR sensor"}
{"cmd": "gpio_set_mode", "pin": 6, "mode": "output", "label": "LED"}
{"cmd": "gpio_set_mode", "pin": 26, "mode": "adc",   "label": "light sensor"}
{"cmd": "gpio_set_mode", "pin": 7, "mode": "pwm",    "label": "servo"}
{"cmd": "gpio_set_mode", "pin": 8, "mode": "unused"}

// Digital read/write
{"cmd": "gpio_read",  "pin": 5}
{"cmd": "gpio_write", "pin": 6, "value": 1}

// ADC read (returns voltage 0.0–3.3 V)
{"cmd": "adc_read", "pin": 26}

// PWM (duty: 0–65535 u16)
{"cmd": "pwm_set", "pin": 7, "freq": 50, "duty": 4915}

// Introspection
{"cmd": "list_pins"}   // all assignable pins with current config
{"cmd": "get_all"}     // only configured (non-unused) pins
```

### RP2040 → Host (replies)

```jsonc
{"ok": true}
{"ok": true, "value": 1}
{"ok": true, "value": 1.6523}
{"ok": true, "pins": [{"pin": 5, "mode": "input", "label": "IR sensor", "value": 0}, ...]}
{"ok": false, "error": "pin 26 not in adc mode"}
```

### RP2040 → Host (async events)

Pushed automatically when a monitored **input** pin changes state:

```jsonc
{"event": "change", "pin": 5, "value": 1}
{"event": "change", "pin": 5, "value": 0}
```

---

## Pin Availability

| Pins | Notes |
|---|---|
| GP1, GP2 | **Reserved** – UART TX/RX. Never reassignable. |
| GP3–GP25 | Free digital I/O or PWM |
| GP26–GP29 | ADC capable (and usable as digital I/O too) |

---

## Updating firmware over USB (no disassembly)

```bash
# While robot is powered on with USB connected to dev machine
mpremote connect auto cp main.py pin_manager.py protocol.py :
mpremote connect auto reset
```

---

## Troubleshooting

**No reply from RP2040** → check UART wiring, confirm GP1↔GPIO15 and GP2↔GPIO14. Make sure ttyAMA0 serial console is disabled on the RPi5.

**`json parse error` reply** → the host sent a malformed frame. Check `coprocessor.py` on the RPi side.

**`pin X not assignable`** → you tried GP1 or GP2 (reserved for UART).

**`cannot set pin X to mode 'adc'`** → only GP26/27/28/29 have ADC hardware on the RP2040.
