# Pico W joystick robot

A Pico W port of `sbroboticsteam/InternalComp_Software` (`beginner_code` branch), with the
stubbed-out parts filled in. The Pico W hosts the joystick web page itself, so you just
connect a phone to it and drive. No laptop or router needed.

```
phone browser ──(Wi-Fi, WebSocket {"x","y"} @ 20 Hz)──> Pico W (Microdot) ──> H-bridge ──> 2 motors
```

## What goes on the Pico

Copy this folder's contents to the root of the Pico so it looks like:

```
/main.py              server + motor logic (runs on boot)
/secrets.py           Wi-Fi mode, network name, password
/lib/microdot/        web server library (v2.7.0, 5 files)
/static/index.html    joystick page
/static/index.css
/static/index.js
```

`README.md` doesn't need to go on the board.

## Uploading with Thonny

1. Flash MicroPython for **Pico W** (not plain Pico, which has no Wi-Fi driver).
2. Turn on **View > Files**. In the top (computer) pane, browse to this folder.
3. Select `main.py`, `secrets.py`, `lib`, and `static`, right-click, and choose
   **Upload to /**. Thonny copies folders recursively.
4. Press the red Stop button (soft reset) or unplug and replug the board. `main.py` starts
   on its own. Thonny's Shell prints the address to open.

To iterate on the server, open `main.py` and press F5. To iterate on the page, edit the
files in `static/`, re-upload them, and refresh the browser (the Pico sends them with
caching off).

## Connecting

Default is **access point mode** (`MODE = "ap"` in `secrets.py`):

1. On your phone, join Wi-Fi **PicoBot-01** with password **drivebot123**. Change these
   per robot if several are running at once.
2. Open **http://192.168.4.1**. The dot at the top turns green when connected.

For **station mode**, set `MODE = "sta"` and fill in `SSID` / `PASSWORD`. Use a home
router or phone hotspot: eduroam and other WPA2-Enterprise networks won't work. The IP is
printed in the Shell, and if it can't join it falls back to AP mode so you aren't locked out.

## Wiring (L298N-style driver, GP numbers)

| Signal          | GP pin | Driver pin   |
|-----------------|--------|--------------|
| Left PWM        | GP3    | ENA          |
| Left dir 1 / 2  | GP0 / GP10 | IN1 / IN2 |
| Right PWM       | **GP18** | ENB        |
| Right dir 1 / 2 | GP20 / GP21 | IN3 / IN4 |
| Ground          | any GND | GND (must be shared) |

**Pin change from the original:** the repo used GP19 for the right PWM. GP3 and GP19 are on
the same RP2040 PWM slice and channel (1B), so both wheels would always get the same duty
cycle and the robot couldn't turn by speed difference. GP18 is the pin right next to GP19.
`main.py` prints a warning at boot if the two PWM pins ever collide again.

Power the motors from their own battery through the driver, not from the Pico's 3V3/VBUS.

## Tuning (top of `main.py`)

| Setting | What it does |
|---------|--------------|
| `INVERT_LEFT` / `INVERT_RIGHT` | Flip a wheel that spins backwards when you push forward |
| `MAX_SPEED` | Overall speed cap, 0–1 |
| `MIN_DUTY` | Raise (around 0.3) if motors hum but don't move at small stick inputs |
| `DEADZONE` | How much stick movement is ignored near center |
| `WATCHDOG_MS` | Motors stop if no command arrives for this long (default 500 ms) |

## Safety behavior

- The page sends a command every 50 ms even when the stick is held still. If the Pico
  hears nothing for 500 ms (Wi-Fi drop, phone locked, tab closed), it stops the motors.
- Releasing the stick, or switching away from the tab, sends an immediate stop.
- The newest browser connection takes control and older ones are ignored, so two phones
  can't fight over the robot.
- Motors are set to stopped before Wi-Fi starts and when the program exits.

## Protocol

WebSocket at `ws://<pico>/direction`. Text frames of JSON:

```json
{"x": 0.25, "y": 0.9}
```

Both values are -1 to 1, with `y` positive meaning forward and `x` positive meaning turn right.
Arcade mixing on the Pico: `left = y + x`, `right = y - x`, scaled down together if either
goes past 1. `GET /test` still returns `hello world` for a quick connectivity check.

To open the page from a laptop file instead of from the Pico, add `?host=<pico ip>` to the URL.
