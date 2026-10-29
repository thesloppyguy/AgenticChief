import hashlib
import json


def canonical_hash(payload: dict) -> str:
    """sha256 over canonical JSON. The same bytes whatever the key order or database round trip."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
