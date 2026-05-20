"""Shared Drive helpers — service factory, folder cache, soft-delete primitive.

The soft-delete pattern is the center of this module. Every destructive Drive
action in gspace routes through `soft_delete`, which moves a file to a
well-known `_delete-later` folder in My Drive instead of calling the real
delete endpoint. The user reviews and empties that folder manually in the
Drive UI — no Claude tool ever touches `files().delete()`.

Why this shape:

1. **No unrecoverable actions from a tool call.** Even with `confirm=True`
   guards elsewhere, a single wrong file ID to a real delete is permanent.
   A soft-delete is one `files().update()` with new parents — trivially
   reversible by moving the file back.
2. **Batch review beats per-call confirmation.** Rather than gating each
   delete behind a prompt, the user handles pending deletions on their own
   schedule. `list_delete_later` gives them the summary they need.
3. **Folder ID is cached per-process.** Creating the folder is idempotent
   (we look up by name first), but each lookup is a Drive API call — caching
   the ID keeps bulk operations cheap.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ..auth import build_service, with_retry

log = logging.getLogger("gspace.tools.drive_common")

DELETE_LATER_NAME = "_delete-later"
FOLDER_MIME = "application/vnd.google-apps.folder"

_folder_cache_lock = threading.Lock()
_folder_id_cache: dict[str, str] = {}


def build_drive():
    return build_service("drive")


def _find_folder_by_name(svc, name: str) -> str | None:
    """Return the ID of a non-trashed folder with this name at My Drive root."""
    q = (
        f"name = '{name}' and "
        f"mimeType = '{FOLDER_MIME}' and "
        f"'root' in parents and trashed = false"
    )
    resp = with_retry(
        lambda: svc.files()
        .list(q=q, fields="files(id,name)", pageSize=10, spaces="drive")
        .execute()
    )
    files = resp.get("files", []) or []
    return files[0]["id"] if files else None


def _create_folder(svc, name: str, parent_id: str = "root") -> str:
    body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    created = with_retry(
        lambda: svc.files().create(body=body, fields="id").execute()
    )
    return created["id"]


def ensure_delete_later_folder(svc=None) -> str:
    """Return the ID of the `_delete-later` folder, creating it if needed.

    Cached per process. Safe under concurrent handler threads.
    """
    with _folder_cache_lock:
        cached = _folder_id_cache.get(DELETE_LATER_NAME)
        if cached:
            return cached
        svc = svc or build_drive()
        fid = _find_folder_by_name(svc, DELETE_LATER_NAME)
        if fid is None:
            fid = _create_folder(svc, DELETE_LATER_NAME)
            log.info("created %s folder id=%s", DELETE_LATER_NAME, fid)
        _folder_id_cache[DELETE_LATER_NAME] = fid
        return fid


def _get_file(
    svc, file_id: str, fields: str = "id,name,parents,mimeType,driveId"
) -> dict[str, Any]:
    return with_retry(
        lambda: svc.files()
        .get(fileId=file_id, fields=fields, supportsAllDrives=True)
        .execute()
    )


def soft_delete(file_id: str, svc=None) -> dict[str, Any]:
    """Move a file into `_delete-later`. Idempotent: a no-op if already there.

    Hard refuses files that live on a Shared Drive (i.e. `driveId` is set on
    the file metadata). The `_delete-later` folder is in My Drive, so the
    cross-drive move would fail at the API level anyway — but refusing
    up-front keeps Shared Drive content safely out of reach regardless of how
    this primitive is called, and produces a cleaner error.
    """
    from ._errors import error

    svc = svc or build_drive()
    meta = _get_file(svc, file_id)
    if meta.get("driveId"):
        return error(
            f"refusing to soft-delete Shared Drive file {file_id!r}. "
            "Delete Shared Drive items from the Drive UI directly.",
            file_id=file_id,
            drive_id=meta["driveId"],
            name=meta.get("name"),
        )
    target = ensure_delete_later_folder(svc)
    current_parents = meta.get("parents", []) or []
    if target in current_parents and len(current_parents) == 1:
        return {
            "ok": True,
            "already_pending": True,
            "file_id": file_id,
            "name": meta.get("name"),
            "delete_later_folder_id": target,
        }
    remove = ",".join(p for p in current_parents if p != target)
    updated = with_retry(
        lambda: svc.files()
        .update(
            fileId=file_id,
            addParents=target,
            removeParents=remove or None,
            fields="id,name,parents",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {
        "ok": True,
        "already_pending": False,
        "file_id": file_id,
        "name": updated.get("name"),
        "previous_parents": current_parents,
        "delete_later_folder_id": target,
    }


def list_delete_later(svc=None, page_size: int = 100) -> dict[str, Any]:
    """List files currently pending user review in the `_delete-later` folder."""
    svc = svc or build_drive()
    target = ensure_delete_later_folder(svc)
    q = f"'{target}' in parents and trashed = false"
    resp = with_retry(
        lambda: svc.files()
        .list(
            q=q,
            fields="files(id,name,mimeType,modifiedTime,size)",
            pageSize=page_size,
            orderBy="modifiedTime desc",
        )
        .execute()
    )
    files = resp.get("files", []) or []
    return {
        "ok": True,
        "delete_later_folder_id": target,
        "count": len(files),
        "files": files,
    }


def reset_folder_cache() -> None:
    """For tests — clear the per-process folder-ID cache."""
    with _folder_cache_lock:
        _folder_id_cache.clear()
