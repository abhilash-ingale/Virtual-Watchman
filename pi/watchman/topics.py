"""MQTT topic contract. Keep in sync with CLAUDE.md section 1."""

EVENT = "door/event"      # Nicla -> Pi: person confirmed
FRAMES = "door/frames"    # Nicla -> Pi: QVGA JPEG frames
CONTROL = "door/control"  # Pi -> Nicla: "stop" returns the Nicla to MONITOR
RESULT = "door/result"    # Pi -> anyone: Abhi / Tanya / Unknown

ALL = "door/#"
