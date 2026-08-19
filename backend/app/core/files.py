import os
import uuid

from fastapi import HTTPException, UploadFile, status

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads/receipts")
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Magic byte signatures so we validate the *actual* file content,
# not just the filename extension or the client-supplied content-type.
SIGNATURES = {
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
    b"%PDF-": ("application/pdf", ".pdf"),
}


def _detect_type(header: bytes):
    for sig, (mime, ext) in SIGNATURES.items():
        if header.startswith(sig):
            return mime, ext
    return None, None


async def save_receipt(file: UploadFile, request_id: str) -> tuple[str, str]:
    """Validates and saves a receipt file. Returns (stored_filename, stored_path)."""
    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Receipt file exceeds the 5 MB size limit",
        )

    mime, ext = _detect_type(contents[:16])
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only JPEG, PNG, and PDF receipts are accepted.",
        )

    request_dir = os.path.join(UPLOAD_DIR, request_id)
    os.makedirs(request_dir, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(request_dir, stored_filename)

    with open(stored_path, "wb") as f:
        f.write(contents)

    return stored_filename, stored_path
