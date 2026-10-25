# Virtual Watchman - Nicla Vision firmware (OpenMV MicroPython).
#
# M1: on-chip person detection with a 4-of-5 debounce driving the
# MONITOR -> BROADCAST -> COOLDOWN state machine. Transitions are printed
# to the OpenMV IDE terminal. MQTT publishing (M2) and JPEG streaming (M3)
# plug into on_broadcast_start() / on_broadcast_frame().
#
# Run: open this file in the OpenMV IDE and press Run, or copy it to the
# board's drive as main.py so it starts on power-up.
#
# The state machine is plain Python with no hardware imports at module
# level, so nicla/tests can exercise it under CPython.

import time

# ---- Tunables ---------------------------------------------------------------

PERSON_THRESHOLD = 0.8       # person score that counts as a "person" frame
DEBOUNCE_WINDOW = 5          # frames remembered
DEBOUNCE_HITS = 4            # person frames within the window to confirm
# 0.7 / 3-of-5 gave occasional false triggers on an empty scene (2026-10-25).
FRAME_INTERVAL_MS = 200      # ~5 fps
BROADCAST_TIMEOUT_MS = 12000  # give up on the Pi's "stop" after this
COOLDOWN_MS = 30000          # quiet period before the next trigger

MODEL_PATHS = ("/rom/person_detect.tflite", "person_detect")

MONITOR = "MONITOR"
BROADCAST = "BROADCAST"
COOLDOWN = "COOLDOWN"


def _ticks_diff(new, old):
    # MicroPython's ticks wrap around; ticks_diff handles that. CPython (tests)
    # has no ticks_diff, and plain subtraction is correct there.
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(new, old)
    return new - old


# ---- Logic (hardware-free) --------------------------------------------------

class Debouncer:
    """True once `hits` of the last `window` frames were person frames."""

    def __init__(self, window=DEBOUNCE_WINDOW, hits=DEBOUNCE_HITS):
        self.window = window
        self.hits = hits
        self._history = []

    def update(self, is_person):
        self._history.append(1 if is_person else 0)
        if len(self._history) > self.window:
            self._history.pop(0)
        return sum(self._history) >= self.hits

    def reset(self):
        self._history = []


class Watchman:
    """MONITOR -> BROADCAST -> COOLDOWN -> MONITOR.

    update() and stop() return the new state when a transition happens,
    otherwise None. `reason` says why the last transition happened.
    """

    def __init__(self, now_ms, threshold=PERSON_THRESHOLD,
                 broadcast_timeout_ms=BROADCAST_TIMEOUT_MS,
                 cooldown_ms=COOLDOWN_MS, debouncer=None):
        self.threshold = threshold
        self.broadcast_timeout_ms = broadcast_timeout_ms
        self.cooldown_ms = cooldown_ms
        self.debouncer = debouncer or Debouncer()
        self.state = MONITOR
        self.since = now_ms
        self.reason = "start"

    def elapsed(self, now_ms):
        return _ticks_diff(now_ms, self.since)

    def _enter(self, state, now_ms, reason):
        self.state = state
        self.since = now_ms
        self.reason = reason
        if state == MONITOR:
            self.debouncer.reset()
        return state

    def update(self, now_ms, score=None):
        """Advance on a new frame. `score` is only used in MONITOR."""
        if self.state == MONITOR:
            if score is not None and self.debouncer.update(score >= self.threshold):
                return self._enter(BROADCAST, now_ms, "person confirmed")
        elif self.state == BROADCAST:
            if self.elapsed(now_ms) >= self.broadcast_timeout_ms:
                return self._enter(COOLDOWN, now_ms, "broadcast timeout")
        elif self.state == COOLDOWN:
            if self.elapsed(now_ms) >= self.cooldown_ms:
                return self._enter(MONITOR, now_ms, "cooldown over")
        return None

    def stop(self, now_ms):
        """The Pi sent `stop` on door/control (wired up in M3)."""
        if self.state == BROADCAST:
            return self._enter(COOLDOWN, now_ms, "stop from Pi")
        return None


# ---- Hardware ---------------------------------------------------------------

class Camera:
    """QVGA RGB565 capture. Uses `csi` (firmware >= 4.7) or falls back to `sensor`."""

    def __init__(self):
        try:
            import csi
            self._cam = csi.CSI()
            self._cam.reset()
            self._cam.pixformat(csi.RGB565)
            self._cam.framesize(csi.QVGA)
            self._cam.snapshot(time=2000)  # let auto exposure settle
        except ImportError:
            import sensor
            sensor.reset()
            sensor.set_pixformat(sensor.RGB565)
            sensor.set_framesize(sensor.QVGA)
            sensor.skip_frames(time=2000)
            self._cam = sensor

    def snapshot(self):
        return self._cam.snapshot()


class Leds:
    """Status LED: off in MONITOR, blue in BROADCAST, red in COOLDOWN."""

    def __init__(self):
        self._leds = {}
        try:
            from machine import LED
            self._leds = {"red": LED("LED_RED"), "green": LED("LED_GREEN"),
                          "blue": LED("LED_BLUE")}
        except Exception:
            pass  # no LEDs is not worth crashing over
        self.show(MONITOR)

    def show(self, state):
        colour = {BROADCAST: "blue", COOLDOWN: "red"}.get(state)
        for name, led in self._leds.items():
            if name == colour:
                led.on()
            else:
                led.off()


def load_model():
    import ml
    last_error = None
    for path in MODEL_PATHS:
        try:
            model = ml.Model(path)
            print("model:", path)
            return model
        except Exception as e:  # OSError / ValueError depending on firmware
            last_error = e
    raise RuntimeError("person_detect model not found: %r" % (last_error,))


def person_index(model):
    labels = getattr(model, "labels", None)
    if labels and "person" in labels:
        return labels.index("person")
    return 1  # person_detect outputs [no_person, person]


def person_score(model, img, index):
    return model.predict([img])[0].flatten().tolist()[index]


def on_broadcast_start():
    print(">>> door/event (M2: publish over MQTT)")


def on_broadcast_frame(img):
    pass  # M3: img.to_jpeg(quality=...) -> publish to door/frames


def run():
    cam = Camera()
    leds = Leds()
    model = load_model()
    index = person_index(model)
    watchman = Watchman(time.ticks_ms())
    previous = None

    print("Virtual Watchman M1: threshold %.2f, %d of %d frames"
          % (PERSON_THRESHOLD, DEBOUNCE_HITS, DEBOUNCE_WINDOW))

    while True:
        started = time.ticks_ms()
        # Real loop rate: start-to-start, so it includes the throttling sleep.
        loop_fps = 0.0
        if previous is not None:
            loop_fps = 1000 / max(1, _ticks_diff(started, previous))
        previous = started
        img = cam.snapshot()

        if watchman.state == MONITOR:
            infer_start = time.ticks_ms()
            score = person_score(model, img, index)
            infer_ms = _ticks_diff(time.ticks_ms(), infer_start)
            changed = watchman.update(started, score)
            print("%-9s person=%.2f  loop %.1f fps  infer %d ms"
                  % (watchman.state, score, loop_fps, infer_ms))
        else:
            changed = watchman.update(started)
            if watchman.state == BROADCAST:
                on_broadcast_frame(img)

        if changed:
            print("=== %s (%s)" % (changed, watchman.reason))
            leds.show(changed)
            if changed == BROADCAST:
                on_broadcast_start()

        spare = FRAME_INTERVAL_MS - _ticks_diff(time.ticks_ms(), started)
        if spare > 0:
            time.sleep_ms(spare)


if __name__ == "__main__":
    run()
