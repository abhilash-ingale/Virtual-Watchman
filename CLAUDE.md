# CLAUDE.md — Virtual Watchman

Front-door person recognition. An Arduino Nicla Vision at the door detects a person and streams frames over MQTT to a Raspberry Pi 4, which recognises **Abhi**, **Tanya** or **Unknown**, notifies, and logs.

Development happens on a Mac inside Docker, so the Pi-side code runs the same everywhere (Mac, Linux, Pi). Only the Nicla firmware lives outside Docker.

---

## 1. System overview

### Hardware
- **Arduino Nicla Vision** at the apartment door (OpenMV MicroPython)
- **Raspberry Pi 4** on the home Wi-Fi (64-bit Raspberry Pi OS, `linux/arm64`)
- **Mac** for development (Docker Desktop)

### Flow
1. **Nicla — MONITOR:** on-chip person / no-person detection (OpenMV `person_detect` or an Edge Impulse model, 96×96 grayscale, ~5 fps). A person is confirmed only when 3 of the last 5 frames say "person".
2. **Nicla — BROADCAST:** on confirmation, publish `door/event`, then stream QVGA JPEG frames to `door/frames`. Return to MONITOR on `stop` from `door/control` or after a 10–15 s timeout, then a ~30 s cooldown before re-triggering.
3. **Pi — RECOGNIZE:** Mosquitto broker. Per frame: detect face (YuNet) → embedding (MobileFaceNet, ONNX Runtime) → cosine similarity against enrolled embeddings. Vote across 5–10 frames → publish `door/result`, send notification with snapshot, log to SQLite, send `stop`.

### MQTT topics
| Topic | Direction | Purpose |
|---|---|---|
| `door/event` | Nicla → Pi | Person confirmed |
| `door/frames` | Nicla → Pi | QVGA JPEG frames |
| `door/control` | Pi → Nicla | `stop` to return to MONITOR |
| `door/result` | Pi → anyone | Abhi / Tanya / Unknown |

### Key design choice
Face **embeddings + similarity threshold**, not a 3-class classifier, so strangers come out as **Unknown**. Adding a person = enrolling ~20 photos, no retraining.

---

## 2. Repository layout (target)

```
Virtual-Watchman/
├── CLAUDE.md
├── docker-compose.yml          # dev stack: broker + recognizer + nicla simulator
├── docker-compose.pi.yml       # override for running on the Raspberry Pi
├── .env.example                # MQTT host, thresholds, notification tokens (copy to .env)
├── mosquitto/
│   └── mosquitto.conf
├── nicla/                      # MicroPython for the Nicla (NOT run in Docker)
│   ├── main.py                 # MONITOR / BROADCAST state machine
│   └── config.py               # Wi-Fi + broker settings (gitignored secrets)
├── pi/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── watchman/
│   │   ├── recognizer.py       # MQTT loop, voting, result publishing
│   │   ├── face.py             # YuNet detection + MobileFaceNet embedding
│   │   ├── enroll.py           # build embeddings from photos
│   │   ├── store.py            # SQLite logging
│   │   └── notify.py           # notification with snapshot
│   ├── tools/
│   │   ├── nicla_sim.py        # replays JPEGs/video as if it were the Nicla
│   │   └── plot_scores.py      # similarity histograms for threshold tuning
│   └── tests/
├── models/                     # YuNet + MobileFaceNet .onnx (downloaded, gitignored)
└── data/                       # gitignored: enrol photos, embeddings, SQLite, snapshots
    ├── enroll/abhi/  enroll/tanya/
    ├── samples/                # recorded door footage for replay
    └── db/
```

---

## 3. Docker development setup (macOS, platform independent)

### Why this shape
- The Pi 4 and Apple Silicon Macs are both `arm64`, so the same image builds and runs on both. On Intel Macs/Linux, Docker builds `amd64` from the same Dockerfile; use `docker buildx --platform linux/arm64` to produce the Pi image.
- **Docker Desktop on macOS cannot pass USB devices or the Mac webcam into containers.** So the Nicla is flashed from the host with the OpenMV IDE, and inside Docker the Nicla is replaced by `nicla_sim.py`, which replays recorded JPEGs/video over MQTT. The real Nicla can still talk to the dockerised broker over Wi-Fi because port 1883 is published to the Mac's LAN IP.
- No GUI in containers: debug images (face boxes, crops) are written to `data/debug/`, which is bind-mounted and viewable on the Mac.

### Prerequisites (Mac)
- A Docker engine: this Mac uses **OrbStack** (`orb start` if `docker` can't reach the daemon); Docker Desktop works too
- OpenMV IDE (host only, for the Nicla)
- Optional: VS Code with the Dev Containers extension to attach to the `recognizer` container

### Services (`docker-compose.yml`)
| Service | Image | Purpose |
|---|---|---|
| `mosquitto` | `eclipse-mosquitto:2` | Broker; port `1883` published so the real Nicla can connect |
| `recognizer` | built from `pi/Dockerfile` | Python 3.11-slim, `opencv-python-headless` (≥4.8 for `FaceDetectorYN`), `onnxruntime`, `paho-mqtt` 2.x, `numpy`; source bind-mounted for live editing |
| `nicla-sim` | same image, `profiles: [sim]` | Runs `tools/nicla_sim.py` against `data/samples/` |

Notes:
- Mosquitto 2 only listens on localhost by default; `mosquitto.conf` needs `listener 1883 0.0.0.0` (and `allow_anonymous true` for dev only; add a password file before deploying).
- Containers reach the broker as `mosquitto:1883`; the Nicla reaches it as `<Mac LAN IP>:1883` during dev and `<Pi IP>:1883` in production. Keep the host in `.env` / `nicla/config.py`, never hardcoded.
- `models/` and `data/` are bind mounts so models are downloaded once and SQLite/snapshots survive rebuilds.

### Everyday commands
```bash
cp .env.example .env
docker compose run --rm recognizer python tools/download_models.py   # once: YuNet + MobileFaceNet into models/
docker compose up -d mosquitto recognizer          # broker + recognizer
docker compose --profile sim up nicla-sim          # replay sample footage
docker compose exec recognizer python -m watchman.enroll --name abhi data/enroll/abhi
docker compose exec recognizer pytest
docker compose exec recognizer python -m pytest -p no:cacheprovider /nicla/tests   # Nicla state machine under CPython
docker compose exec mosquitto mosquitto_sub -t 'door/#' -v   # watch all traffic
docker compose logs -f recognizer
```

### Deploying to the Pi
```bash
docker buildx build --platform linux/arm64 -t watchman-recognizer:latest pi/   # or build directly on the Pi
docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d
```
`docker-compose.pi.yml` drops the source bind mount and the simulator, sets `restart: unless-stopped`, and points volumes at persistent paths on the Pi.

---

## 4. Milestone plan

Each milestone ends with something you can demo. Pi-side milestones are developed in Docker on the Mac first, then run on the Pi unchanged.

### M0 — Docker dev environment
- [x] `docker-compose.yml`, `mosquitto.conf`, `pi/Dockerfile`, `requirements.txt`, `.env.example`, `.gitignore`
- [x] Script to download YuNet and MobileFaceNet ONNX into `models/` (`pi/tools/download_models.py`; run and SHA-256 pinned 2026-10-25. MobileFaceNet takes 112×112 RGB, outputs a 512-d embedding)
- [x] **Done when:** *(verified 2026-10-25, incl. publish via Mac LAN IP and broker-restart reconnect)* `docker compose up` starts the broker and a recognizer stub that logs every `door/#` message; `mosquitto_pub` from the host is seen by the stub.

### M1 — Nicla detection in the OpenMV IDE *(host, no Docker)*
- [x] `nicla/main.py`: person detection at ~5 fps with debounce, now threshold 0.8 and 4 of 5 frames after 0.7 / 3-of-5 gave false triggers on an empty scene (built-in `/rom/person_detect.tflite` via `ml`; `csi` camera API with `sensor` fallback for firmware < 4.7)
- [x] MONITOR / BROADCAST / COOLDOWN state machine, 12 s timeout, 30 s cooldown; LED off / blue / red
- [x] Hardware-free logic unit-tested under CPython (`nicla/tests`), MicroPython syntax checked with `mpy-cross`
- [ ] **Done when:** the IDE terminal prints confirmed events reliably with few false triggers. *(needs the real board)*

Running on the board: OpenMV IDE → connect → open `nicla/main.py` → Run. The terminal prints `state person=score loop <fps> infer <ms>` per frame (loop rate includes the throttle; infer is model time only) and `=== STATE (reason)` on transitions. To start on power-up, save it to the board's drive as `main.py`. Tune `PERSON_THRESHOLD` and the debounce at the top of the file.

### M2 — MQTT event reaches the broker
- [ ] Nicla connects to Wi-Fi and the dockerised broker on the Mac; publishes `door/event`
- [ ] Wi-Fi/broker failure never hangs the Nicla: reconnect with backoff, always fall back to MONITOR
- [ ] **Done when:** `mosquitto_sub` in the container shows events from the real Nicla.

### M3 — JPEG streaming Nicla → broker
- [ ] Stream QVGA JPEG to `door/frames`; obey `stop` on `door/control`
- [ ] `nicla_sim.py` mimics the same protocol (event, frames, honours `stop`)
- [ ] Recorder in the recognizer that saves incoming frames to `data/samples/` for later replay
- [ ] **Done when:** frames from both the real Nicla and the simulator are saved and viewable on the Mac.

### M4 — Enrolment and recognition (container only)
- [ ] `face.py`: YuNet detection, alignment, MobileFaceNet embedding (L2-normalised)
- [ ] `enroll.py`: ~20 photos per person → stored mean/all embeddings
- [ ] `plot_scores.py`: genuine vs impostor similarity histograms → pick threshold from data
- [ ] Unit tests on fixed images
- [ ] **Done when:** offline evaluation on saved samples gives correct Abhi / Tanya / Unknown.

### M5 — Full loop end to end
- [ ] `recognizer.py`: on `door/event`, collect 5–10 frames, vote, publish `door/result`, send `stop`
- [ ] `store.py` SQLite log (time, result, score, snapshot path); `notify.py` with snapshot
- [ ] **Done when:** simulator → result in Docker on the Mac, then real Nicla → result on the Pi.

### M6 — Tuning with real footage
- [ ] Record real door footage, including evenings; replay through the simulator
- [ ] Retune threshold, vote count, minimum face size, timeouts
- [ ] **Done when:** acceptable false-accept / false-reject rates across lighting conditions.

### Stretch goals
- Face detection on the Nicla, sending only face crops
- PIR wake-up so the Nicla can sleep and run on battery
- OAK camera inside the door as a second viewpoint

### Parked topics (revisit later)
- **Scene-clear re-arm:** return from COOLDOWN to MONITOR only after ~3 s of clearly empty frames (plus a short minimum cooldown) instead of a fixed 30 s. Closes the "second person within 30 s is missed" gap. Needs reliable empty-scene scores, so revisit with M6 footage. Fixed 30 s kept for now.
- **ToF + camera fusion:** the Nicla Vision has an on-board VL53L1X time-of-flight sensor (driver frozen into the firmware as `vl53l1x`). Use distance (something within ~0.5–2 m, or a sudden change) together with the person score to confirm a person, to cut false triggers from exposure jumps or person-like shapes, and possibly as a cheap wake-up signal before running the model.

---

## 5. Watch out for
- **Dim hallway lighting** — the Nicla has no IR; test evenings early.
- **Camera height** — mount at roughly face height.
- **Wi-Fi dropouts** — the Nicla must time out back to MONITOR, never hang.
- **Threshold** — choose it from plotted scores, not by guessing.
- **Privacy / GDPR** — filming shared hallways is restricted; keep face data on the Pi only (never in images or the repo), and get Tanya's consent. `data/` and `models/` are gitignored.
- **Docker on macOS** — no USB/webcam passthrough; use the simulator and recorded samples.

---

## 6. Conventions for Claude
- Pi-side code is Python 3.11, runs inside the `recognizer` container; run tests and tools via `docker compose exec recognizer …`, not on the host.
- Nicla code is OpenMV MicroPython: no third-party packages, keep memory use small, avoid blocking calls without timeouts.
- Config (broker host, thresholds, tokens) comes from environment variables / `.env`; never hardcode IPs or secrets.
- Never commit face images, embeddings, the SQLite DB or `.env`.
- Keep the MQTT topic contract in section 1 as the single source of truth; update it here if it changes.

## Current status / next step
M0 done (2026-10-25). M1 code written and tested off-device; next: run it on the Nicla in the OpenMV IDE and tune the threshold, then **M2** — MQTT `door/event` to the broker.
