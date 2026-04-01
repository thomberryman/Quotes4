from __future__ import annotations

import re
from pathlib import PurePosixPath

_SAFE_STORAGE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")


def validate_storage_object_key(value: str) -> str:
    object_key = str(value).strip()
    if not object_key:
        raise ValueError("Storage object key is required.")
    if object_key.startswith("/"):
        raise ValueError("Storage object key must not be an absolute path.")
    if "://" in object_key:
        raise ValueError("Storage object key must not be a URL.")
    if "\\" in object_key:
        raise ValueError("Storage object key must not contain backslashes.")
    path = PurePosixPath(object_key)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Storage object key contains an invalid path segment.")
    if not _SAFE_STORAGE_KEY_RE.match(object_key):
        raise ValueError("Storage object key contains unsupported characters.")
    return object_key
