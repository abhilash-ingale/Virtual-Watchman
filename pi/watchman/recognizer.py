"""Recognizer service.

M0 stub: connects to the broker, subscribes to door/#, and logs every message.
Recognition (YuNet + MobileFaceNet + voting) replaces the logging in M4/M5.
"""
import logging
import signal
import sys

import paho.mqtt.client as mqtt

from watchman import config, topics

log = logging.getLogger("watchman.recognizer")

JPEG_MAGIC = b"\xff\xd8"


def describe(topic: str, payload: bytes) -> str:
    """One-line, human-readable summary of an MQTT message."""
    if topic == topics.FRAMES:
        kind = "jpeg" if payload.startswith(JPEG_MAGIC) else "binary"
        return f"{topic}: {kind} frame, {len(payload)} bytes"
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return f"{topic}: {len(payload)} bytes (binary)"
    if len(text) > 200:
        text = text[:200] + "..."
    return f"{topic}: {text}"


def log_runtime_versions() -> None:
    """Log versions of the heavy dependencies so a broken image fails loudly at start."""
    import cv2
    import numpy
    import onnxruntime

    log.info(
        "opencv %s (FaceDetectorYN: %s), onnxruntime %s, numpy %s",
        cv2.__version__,
        hasattr(cv2, "FaceDetectorYN"),
        onnxruntime.__version__,
        numpy.__version__,
    )


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        log.error("broker refused connection: %s", reason_code)
        return
    log.info("connected to broker, subscribing to %s", topics.ALL)
    client.subscribe(topics.ALL, qos=0)


def on_disconnect(client, userdata, flags, reason_code, properties):
    log.warning("disconnected from broker (%s); paho will reconnect", reason_code)


def on_message(client, userdata, msg):
    log.info(describe(msg.topic, msg.payload))


def main() -> int:
    cfg = config.load()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log_runtime_versions()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="watchman-recognizer")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    signal.signal(signal.SIGTERM, lambda *_: client.disconnect())

    log.info("connecting to %s:%d", cfg.mqtt_host, cfg.mqtt_port)
    client.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=30)
    try:
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
