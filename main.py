# Pico W joystick robot server (MicroPython + Microdot)
#
# Based on sbroboticsteam/InternalComp_Software (beginner_code branch).
# A phone or laptop opens the joystick page served by the Pico, the page sends
# {"x": -1..1, "y": -1..1} over a WebSocket ~20 times a second, and this file
# mixes that into left/right wheel speeds for a two-motor H-bridge driver
# (L298N-style: one PWM enable pin + two direction pins per motor).

import asyncio
import json
import time

import network
from machine import Pin, PWM
from microdot import Microdot, Response
from microdot.cors import CORS
from microdot.websocket import with_websocket

import secrets

# ---------------------------------------------------------------------------
# Pin setup  (GP numbers, not physical pin numbers)
#
# The original repo used GP3 and GP19 for the two PWM pins. On the RP2040 those
# two land on the SAME PWM slice and channel (1B), so they always output the
# same duty cycle: you could never drive the wheels at different speeds. The
# right motor's PWM moves to GP18 (slice 1A), which is the pin right next to
# GP19 on the board, so it's a one-wire move.
# ---------------------------------------------------------------------------
LEFT_PWM, LEFT_IN1, LEFT_IN2 = 3, 0, 10
RIGHT_PWM, RIGHT_IN1, RIGHT_IN2 = 18, 20, 21

PWM_FREQ = 1000          # Hz, same as the original
INVERT_LEFT = False      # flip if a wheel spins backwards when you push forward
INVERT_RIGHT = False

DEADZONE = 0.08          # ignore tiny stick movements near the center
MAX_SPEED = 1.0          # 0..1, lower it to make the robot gentler
MIN_DUTY = 0.0           # 0..1, raise (e.g. 0.3) if motors hum but don't turn at low stick
WATCHDOG_MS = 500        # stop the motors if no command arrives for this long

try:
    from time import ticks_ms, ticks_diff
except ImportError:      # lets this file run under desktop Python for testing
    def ticks_ms():
        return int(time.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b


def pwm_slot(gpio):
    return (gpio >> 1) % 8, "AB"[gpio & 1]


if pwm_slot(LEFT_PWM) == pwm_slot(RIGHT_PWM):
    print("WARNING: GP%d and GP%d share PWM slice %d%s; both wheels will "
          "always get the same speed." % ((LEFT_PWM, RIGHT_PWM) + pwm_slot(LEFT_PWM)))


class Motor:
    def __init__(self, pwm_pin, in1_pin, in2_pin, invert=False):
        self.pwm = PWM(Pin(pwm_pin, Pin.OUT), freq=PWM_FREQ)
        self.in1 = Pin(in1_pin, Pin.OUT)
        self.in2 = Pin(in2_pin, Pin.OUT)
        self.invert = invert
        self.set(0)

    def set(self, speed):
        """speed in -1..1. Positive = forward."""
        speed = max(-1.0, min(1.0, speed))
        if self.invert:
            speed = -speed
        if speed > 0:
            self.in1.value(1)
            self.in2.value(0)
        elif speed < 0:
            self.in1.value(0)
            self.in2.value(1)
        else:
            self.in1.value(0)
            self.in2.value(0)
        mag = abs(speed)
        if mag > 0:
            mag = MIN_DUTY + (1 - MIN_DUTY) * mag
        self.pwm.duty_u16(int(mag * 65535))


left = Motor(LEFT_PWM, LEFT_IN1, LEFT_IN2, INVERT_LEFT)
right = Motor(RIGHT_PWM, RIGHT_IN1, RIGHT_IN2, INVERT_RIGHT)
led = Pin("LED", Pin.OUT)


def stop():
    left.set(0)
    right.set(0)


def drive(x, y):
    """Arcade drive: y = forward/back, x = turn. Both -1..1."""
    if abs(x) < DEADZONE:
        x = 0.0
    if abs(y) < DEADZONE:
        y = 0.0
    l = y + x
    r = y - x
    # Scale down so neither side exceeds 1 while keeping the ratio (turn shape)
    m = max(1.0, abs(l), abs(r))
    left.set(l / m * MAX_SPEED)
    right.set(r / m * MAX_SPEED)
    return l / m * MAX_SPEED, r / m * MAX_SPEED


def parse(data):
    """Returns (x, y) clamped to -1..1, or None if the message is bad."""
    try:
        msg = json.loads(data)
        x = float(msg["x"])
        y = float(msg["y"])
    except Exception:
        return None
    if x != x or y != y:     # NaN
        return None
    return max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))


# ---------------------------------------------------------------------------
# Wi-Fi
# ---------------------------------------------------------------------------
def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.config(essid=secrets.AP_SSID, password=secrets.AP_PASSWORD)
    ap.active(True)
    while not ap.active():
        time.sleep(0.1)
    ip = ap.ifconfig()[0]
    print("Access point '%s' up. Join it and open http://%s" % (secrets.AP_SSID, ip))
    return ip


def start_sta(timeout_s=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        wlan.config(pm=network.WLAN.PM_NONE)   # no power saving = lower latency
    except Exception:
        pass
    wlan.connect(secrets.SSID, secrets.PASSWORD)
    start = time.time()
    while not wlan.isconnected() and time.time() - start < timeout_s:
        print("Connecting to %s..." % secrets.SSID)
        time.sleep(1)
    if not wlan.isconnected():
        print("Could not join %s, falling back to access point mode." % secrets.SSID)
        wlan.active(False)
        return None
    ip = wlan.ifconfig()[0]
    print("Connected. Open http://%s" % ip)
    return ip


def connect_wifi():
    try:
        network.country("US")
    except Exception:
        pass
    if getattr(secrets, "MODE", "ap") == "sta":
        ip = start_sta()
        if ip:
            return ip
    return start_ap()


# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------
app = Microdot()
CORS(app, allowed_origins="*", allow_credentials=True)

state = {"last_cmd": ticks_ms(), "owner": None, "next_id": 0}


@app.get("/")
async def index(request):
    return Response.send_file("static/index.html")


@app.get("/test")
async def test(request):
    return "hello world"


@app.get("/direction")
@with_websocket
async def direction(request, ws):
    # Newest connection takes control; older tabs/phones are ignored.
    state["next_id"] += 1
    me = state["next_id"]
    state["owner"] = me
    state["last_cmd"] = ticks_ms()
    led.value(1)
    print("Controller %d connected" % me)
    try:
        while True:
            data = await ws.receive()
            if state["owner"] != me:
                continue
            cmd = parse(data)
            if cmd is None:
                continue
            state["last_cmd"] = ticks_ms()
            drive(*cmd)
    except Exception as e:
        print("WebSocket %d closed: %s" % (me, e))
    finally:
        if state["owner"] == me:
            state["owner"] = None
            stop()
            led.value(0)
        print("Controller %d disconnected" % me)


# Serves index.css, index.js, etc. out of /static. Registered last so it
# doesn't shadow /test or /direction.
@app.get("/<path:path>")
async def static(request, path):
    if ".." in path:
        return "Not found", 404
    try:
        open("static/" + path).close()
    except OSError:
        return "Not found", 404
    return Response.send_file("static/" + path, max_age=0)


async def watchdog():
    """Stop the robot if commands stop arriving (Wi-Fi drop, phone locks...)."""
    stopped = True
    while True:
        await asyncio.sleep(0.05)
        stale = ticks_diff(ticks_ms(), state["last_cmd"]) > WATCHDOG_MS
        if stale and not stopped:
            stop()
            print("Watchdog: no commands for %d ms, motors stopped" % WATCHDOG_MS)
            stopped = True
        elif not stale:
            stopped = False


async def main():
    asyncio.create_task(watchdog())
    await app.start_server(port=getattr(secrets, "PORT", 80))


stop()
connect_wifi()
try:
    asyncio.run(main())
finally:
    stop()
    led.value(0)
