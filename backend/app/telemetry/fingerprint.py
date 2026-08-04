from hashlib import sha256
import json

from app.telemetry.schemas import TelemetryPayload


def fingerprint(payload: TelemetryPayload) -> str:
    """Stable identity for an exact delivery retry, independent of JSON key order."""
    body = {
        "device_id": str(payload.device_id),
        "pole_id": str(payload.pole_id),
        "ts": payload.ts.isoformat(),
        "seq": payload.seq,
        "event_type": payload.event_type,
        "energized": payload.energized,
        "firmware": payload.firmware,
        "battery": payload.battery,
        "rssi": payload.rssi,
    }
    return sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
