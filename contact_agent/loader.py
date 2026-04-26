import json

REQUIRED_KEYS = ["case_id", "missing_fields", "can_proceed"]

def load_missing_info_request(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"missing_info_request.json missing required keys: {missing}")
    return data