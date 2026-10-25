"""Runtime configuration, read from environment variables (see .env.example)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mqtt_host: str
    mqtt_port: int
    log_level: str


def load() -> Config:
    return Config(
        mqtt_host=os.environ.get("MQTT_HOST", "localhost"),
        mqtt_port=int(os.environ.get("MQTT_PORT", "1883")),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
