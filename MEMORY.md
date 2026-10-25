# Virtual Watchman (front-door person recognition)

## Hardware
- Arduino Nicla Vision at the apartment door
- Raspberry Pi 4 on the home Wi-Fi

## Flow
1. **Nicla, MONITOR mode:** runs on-chip person / no-person detection (OpenMV `person_detect` or an Edge Impulse model, 96×96 grayscale, about 5 fps). It confirms a person only when 3 of the last 5 frames say "person".
2. **Nicla, BROADCAST mode:** when a person is confirmed, it publishes `door/event`, then streams QVGA JPEG frames to `door/frames` over MQTT. It returns to MONITOR when the Pi sends `stop` on `door/control`, or after a 10–15 s timeout, then waits about 30 s before it can trigger again.
3. **Pi, RECOGNIZE mode:** runs a Mosquitto broker. For each frame it finds the face (YuNet), turns it into an embedding (MobileFaceNet via ONNX Runtime) and compares it with the enrolled embeddings for Abhi and Tanya using cosine similarity. It votes across 5–10 frames, answers **Abhi**, **Tanya** or **Unknown**, publishes `door/result`, sends a notification with a snapshot, logs to SQLite, then sends `stop`.

## MQTT topics
| Topic | Direction | Purpose |
|---|---|---|
| `door/event` | Nicla → Pi | Person confirmed |
| `door/frames` | Nicla → Pi | QVGA JPEG frames |
| `door/control` | Pi → Nicla | `stop` to return to MONITOR |
| `door/result` | Pi → anyone | Abhi / Tanya / Unknown |

## Key design choice
Use face embeddings with a similarity threshold, not a 3-class classifier, so strangers come out as **Unknown**. Adding a person means enrolling about 20 photos, not retraining.

## Milestones
1. Nicla detection running in the OpenMV IDE.
2. MQTT event reaching the Pi.
3. JPEG streaming from the Nicla to the Pi.
4. Enrolment and recognition tested on the Pi alone.
5. The full loop connected end to end.
6. Tuning with real door footage and evening light.

## Watch out for
- Dim hallway lighting (the Nicla has no infrared)
- Camera mounting height (aim for roughly face height)
- Wi-Fi dropouts (the Nicla must time out back to MONITOR, never hang)
- Similarity threshold: choose it from plotted scores, not by guessing
- GDPR limits on filming shared hallways; keep face data on the Pi and get Tanya's consent

## Stretch goals
- Face detection on the Nicla, sending only face crops
- PIR wake-up so the Nicla can sleep and run on battery
- OAK camera inside the door as a second viewpoint

## Next step
Milestone 1: the OpenMV person-detection script for the Nicla Vision, with the debounce logic.
