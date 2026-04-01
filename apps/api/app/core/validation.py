from __future__ import annotations

import base64
import binascii
import re
from pathlib import PurePosixPath

from app.models.enums import UploadedFileCategory

MAX_GENERIC_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024
MAX_CETA_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
MAX_PDF_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024

QUOTE_PDF_CONTENT_TYPES = frozenset({"application/pdf"})
CETA_EXPORT_CONTENT_TYPES = frozenset(
    {
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "text/plain",
    }
)

_MIME_TYPE_RE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")
_CONTROL_CHARACTER_RE = re.compile(r"[\x00-\x1f\x7f]")
_SAFE_STORAGE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")


def normalize_file_name(value: str) -> str:
    file_name = str(value).strip()
    if not file_name:
        raise ValueError("File name is required.")
    if len(file_name) > 160:
        raise ValueError("File name must be 160 characters or fewer.")
    if "/" in file_name or "\\" in file_name:
        raise ValueError("File name must not include path separators.")
    if file_name.startswith("."):
        raise ValueError("File name must not start with a dot.")
    if _CONTROL_CHARACTER_RE.search(file_name):
        raise ValueError("File name contains invalid control characters.")
    return file_name


def normalize_content_type(value: str) -> str:
    content_type = str(value).strip().lower()
    if not content_type:
        raise ValueError("Content type is required.")
    if not _MIME_TYPE_RE.match(content_type):
        raise ValueError("Content type must be a valid MIME type.")
    return content_type


def normalize_sha256_checksum(value: str) -> str:
    checksum = str(value).strip()
    if not checksum:
        raise ValueError("SHA-256 checksum is required.")
    try:
        digest = base64.b64decode(checksum, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("SHA-256 checksum must be valid base64.") from exc
    if len(digest) != 32:
        raise ValueError("SHA-256 checksum must decode to 32 bytes.")
    return checksum


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


def validate_upload_metadata(
    *,
    file_name: str,
    content_type: str,
    size_bytes: int,
    checksum_sha256: str,
    file_category: UploadedFileCategory | None,
) -> tuple[str, str, str]:
    normalized_file_name = normalize_file_name(file_name)
    normalized_content_type = normalize_content_type(content_type)
    normalized_checksum = normalize_sha256_checksum(checksum_sha256)

    if size_bytes <= 0:
        raise ValueError("File size must be greater than zero.")

    extension = ""
    if "." in normalized_file_name:
        extension = normalized_file_name.rsplit(".", maxsplit=1)[1].lower()

    max_size_bytes = MAX_GENERIC_UPLOAD_SIZE_BYTES
    if file_category == UploadedFileCategory.quote_pdf:
        if normalized_content_type not in QUOTE_PDF_CONTENT_TYPES or extension != "pdf":
            raise ValueError("Quote PDFs must be uploaded as PDF files.")
        max_size_bytes = MAX_PDF_UPLOAD_SIZE_BYTES
    elif file_category == UploadedFileCategory.ceta_export:
        if normalized_content_type not in CETA_EXPORT_CONTENT_TYPES:
            raise ValueError("CETA exports must use a supported CSV or spreadsheet content type.")
        if extension not in {"csv", "xls", "xlsx"}:
            raise ValueError("CETA exports must be .csv, .xls, or .xlsx files.")
        max_size_bytes = MAX_CETA_UPLOAD_SIZE_BYTES

    if size_bytes > max_size_bytes:
        raise ValueError(f"File exceeds the maximum allowed size of {max_size_bytes} bytes.")

    return normalized_file_name, normalized_content_type, normalized_checksum
