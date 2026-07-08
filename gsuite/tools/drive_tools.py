"""Drive tools — search, list, move, rename, share, create folder, soft-delete.

All destructive-looking tools route through `drive_common.soft_delete` — this
module never calls `files().delete()` directly. When the user decides to
actually purge pending items, they open the `_delete-later` folder in the
Drive web UI and empty it there.

Search/list tools default to a lean field set (`id,name,mimeType,modifiedTime`)
so responses stay small across big folders; callers that need more request
extra fields explicitly.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from googleapiclient.http import MediaInMemoryUpload

from ..auth import with_retry
from . import drive_common
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.drive")

DEFAULT_FIELDS = "files(id,name,mimeType,modifiedTime,parents,owners(emailAddress))"
VALID_SHARE_ROLES = {"reader", "commenter", "writer"}

# Google-native docs have no downloadable bytes — they must be *exported* to a
# concrete format. Map each editor type to the text export we return.
GOOGLE_NATIVE_EXPORT = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _svc():
    return drive_common.build_drive()


# --- read --------------------------------------------------------------------

@tool(
    name="drive_search",
    feature="drive.read",
    description=(
        "Search Drive with Google's query syntax (e.g. \"name contains 'invoice' "
        "and mimeType='application/pdf'\"). Returns id, name, mimeType, "
        "modifiedTime, parents, owner email, and driveId when the file lives "
        "on a Shared Drive. Default limit 50. Pass `drive_id` to scope the "
        "search to one Shared Drive."
    ),
    input_schema={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 1000},
            "drive_id": {
                "type": "string",
                "description": "Restrict search to a specific Shared Drive ID.",
            },
        },
    },
)
def drive_search(
    query: str, limit: int = 50, drive_id: str | None = None
) -> dict[str, Any]:
    svc = _svc()
    # Include driveId in the returned fields so callers can distinguish
    # Shared-Drive items from My-Drive/Shared-with-me items without a
    # follow-up metadata call.
    fields = f"nextPageToken,files(id,name,mimeType,modifiedTime,parents,driveId,owners(emailAddress))"
    params: dict[str, Any] = {
        "q": query,
        "fields": fields,
        "pageSize": min(limit, 100),
        "orderBy": "modifiedTime desc",
        "includeItemsFromAllDrives": True,
        "supportsAllDrives": True,
    }
    if drive_id:
        params["corpora"] = "drive"
        params["driveId"] = drive_id
    else:
        params["corpora"] = "allDrives"
    resp = with_retry(lambda: svc.files().list(**params).execute())
    files = resp.get("files", []) or []
    return {"ok": True, "drive_id": drive_id, "count": len(files), "files": files[:limit]}


@tool(
    name="drive_list_folder",
    feature="drive.read",
    description=(
        "List the contents of a Drive folder. Pass `folder_id='root'` (default) "
        "for My Drive. Returns id, name, mimeType, modifiedTime, parents."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "folder_id": {"type": "string", "default": "root"},
            "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 1000},
        },
    },
)
def drive_list_folder(folder_id: str = "root", limit: int = 100) -> dict[str, Any]:
    svc = _svc()
    q = f"'{folder_id}' in parents and trashed = false"
    resp = with_retry(
        lambda: svc.files()
        .list(
            q=q,
            fields=f"nextPageToken,{DEFAULT_FIELDS}",
            pageSize=min(limit, 100),
            orderBy="folder,name",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            corpora="allDrives",
        )
        .execute()
    )
    files = resp.get("files", []) or []
    return {"ok": True, "folder_id": folder_id, "count": len(files), "files": files[:limit]}


@tool(
    name="drive_list_delete_later",
    feature="drive.read",
    description=(
        "List files pending manual review in the `_delete-later` folder. "
        "Use this to summarize what's queued before emptying the folder in the "
        "Drive web UI."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 1000},
        },
    },
)
def drive_list_delete_later(limit: int = 100) -> dict[str, Any]:
    return drive_common.list_delete_later(page_size=limit)


@tool(
    name="drive_get_metadata",
    feature="drive.read",
    description=(
        "Fetch metadata for a file or folder by ID. Returns id, name, mimeType, "
        "parents, driveId (present when the item is on a Shared Drive), owners, "
        "modifiedTime, size. Works across My Drive, Shared with me, and Shared "
        "Drives. Use this to resolve a bare ID (e.g. from a `parents` list) to "
        "its human-readable name."
    ),
    input_schema={
        "type": "object",
        "required": ["file_id"],
        "properties": {"file_id": {"type": "string"}},
    },
)
def drive_get_metadata(file_id: str) -> dict[str, Any]:
    svc = _svc()
    fields = (
        "id,name,mimeType,parents,driveId,modifiedTime,size,"
        "owners(emailAddress,displayName),webViewLink"
    )
    meta = with_retry(
        lambda: svc.files()
        .get(fileId=file_id, fields=fields, supportsAllDrives=True)
        .execute()
    )
    return {"ok": True, **meta}


@tool(
    name="drive_read_file",
    feature="drive.read",
    description=(
        "Read a Drive file's content by id. Google-native Docs/Sheets/Slides "
        "are exported to text (Docs→plain, Sheets→CSV) — for richer structure "
        "prefer `docs_read`/`sheets_read`. Other files (PDF, txt, CSV, images) "
        "are downloaded raw. UTF-8 text is returned in `content`; binary is "
        "base64 in `content` with `encoding='base64'`. Truncated to `max_bytes` "
        "(default 1 MB); `truncated=True` when it was cut."
    ),
    input_schema={
        "type": "object",
        "required": ["file_id"],
        "properties": {
            "file_id": {"type": "string"},
            "max_bytes": {
                "type": "integer",
                "default": 1_000_000,
                "minimum": 1,
                "maximum": 10_000_000,
            },
        },
    },
)
def drive_read_file(file_id: str, max_bytes: int = 1_000_000) -> dict[str, Any]:
    svc = _svc()
    meta = with_retry(
        lambda: svc.files()
        .get(fileId=file_id, fields="id,name,mimeType,size", supportsAllDrives=True)
        .execute()
    )
    mime = meta.get("mimeType", "")
    if mime in GOOGLE_NATIVE_EXPORT:
        export_mime = GOOGLE_NATIVE_EXPORT[mime]
        data: bytes = with_retry(
            lambda: svc.files().export_media(fileId=file_id, mimeType=export_mime).execute()
        )
    elif mime.startswith("application/vnd.google-apps."):
        return error(f"cannot read Google-native type {mime!r} (no text export)")
    else:
        data = with_retry(
            lambda: svc.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
        )
    truncated = len(data) > max_bytes
    data = data[:max_bytes]
    out: dict[str, Any] = {
        "ok": True,
        "id": file_id,
        "name": meta.get("name"),
        "mimeType": mime,
        "bytes": len(data),
        "truncated": truncated,
    }
    try:
        out["content"] = data.decode("utf-8")
        out["encoding"] = "utf-8"
    except UnicodeDecodeError:
        out["content"] = base64.b64encode(data).decode("ascii")
        out["encoding"] = "base64"
    return out


# --- write -------------------------------------------------------------------

@tool(
    name="drive_create_folder",
    feature="drive.write",
    description=(
        "Create a folder. Parent defaults to My Drive root; pass `parent_id` "
        "to nest inside another folder."
    ),
    input_schema={
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "parent_id": {"type": "string", "default": "root"},
        },
    },
)
def drive_create_folder(name: str, parent_id: str = "root") -> dict[str, Any]:
    svc = _svc()
    body = {"name": name, "mimeType": drive_common.FOLDER_MIME, "parents": [parent_id]}
    created = with_retry(
        lambda: svc.files()
        .create(body=body, fields="id,name,parents", supportsAllDrives=True)
        .execute()
    )
    return {"ok": True, **created}


@tool(
    name="drive_create_file",
    feature="drive.write",
    description=(
        "Create a file in Drive with text content. Pass `mime_type` to control "
        "the stored type (default 'text/markdown' so `.md` notes upload as raw "
        "Markdown, not a converted Google Doc). Parent defaults to My Drive root; "
        "pass `parent_id` to nest in a folder. For a native Google Doc/Sheet/Slide "
        "use the docs_/sheets_/slides_ create tools instead. Returns id, name, "
        "mimeType, parents, webViewLink."
    ),
    input_schema={
        "type": "object",
        "required": ["name", "content"],
        "properties": {
            "name": {
                "type": "string",
                "description": "File name including extension, e.g. 'notes.md'.",
            },
            "content": {"type": "string", "description": "UTF-8 text body."},
            "mime_type": {"type": "string", "default": "text/markdown"},
            "parent_id": {"type": "string", "default": "root"},
        },
    },
)
def drive_create_file(
    name: str,
    content: str,
    mime_type: str = "text/markdown",
    parent_id: str = "root",
) -> dict[str, Any]:
    svc = _svc()
    body = {"name": name, "parents": [parent_id], "mimeType": mime_type}
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type)
    created = with_retry(
        lambda: svc.files()
        .create(
            body=body,
            media_body=media,
            fields="id,name,mimeType,parents,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {"ok": True, **created}


@tool(
    name="drive_rename",
    feature="drive.write",
    description="Rename a Drive file or folder by ID.",
    input_schema={
        "type": "object",
        "required": ["file_id", "new_name"],
        "properties": {
            "file_id": {"type": "string"},
            "new_name": {"type": "string"},
        },
    },
)
def drive_rename(file_id: str, new_name: str) -> dict[str, Any]:
    svc = _svc()
    updated = with_retry(
        lambda: svc.files()
        .update(
            fileId=file_id,
            body={"name": new_name},
            fields="id,name",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {"ok": True, **updated}


@tool(
    name="drive_move",
    feature="drive.write",
    description=(
        "Move a file or folder to a new parent. Removes all existing parents "
        "and adds `new_parent_id`. Use `drive_create_folder` first if the "
        "destination doesn't exist yet."
    ),
    input_schema={
        "type": "object",
        "required": ["file_id", "new_parent_id"],
        "properties": {
            "file_id": {"type": "string"},
            "new_parent_id": {"type": "string"},
        },
    },
)
def drive_move(file_id: str, new_parent_id: str) -> dict[str, Any]:
    svc = _svc()
    meta = with_retry(
        lambda: svc.files()
        .get(fileId=file_id, fields="id,name,parents", supportsAllDrives=True)
        .execute()
    )
    current = meta.get("parents", []) or []
    if current == [new_parent_id]:
        return {"ok": True, "unchanged": True, **meta}
    remove = ",".join(p for p in current if p != new_parent_id)
    updated = with_retry(
        lambda: svc.files()
        .update(
            fileId=file_id,
            addParents=new_parent_id,
            removeParents=remove or None,
            fields="id,name,parents",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {"ok": True, "previous_parents": current, **updated}


@tool(
    name="drive_share",
    feature="drive.write",
    description=(
        "Share a file with a user. Role must be `reader`, `commenter`, or "
        "`writer`. Pass `notify=true` to send Google's standard share email."
    ),
    input_schema={
        "type": "object",
        "required": ["file_id", "email"],
        "properties": {
            "file_id": {"type": "string"},
            "email": {"type": "string", "format": "email"},
            "role": {
                "type": "string",
                "enum": ["reader", "commenter", "writer"],
                "default": "reader",
            },
            "notify": {"type": "boolean", "default": False},
        },
    },
)
def drive_share(
    file_id: str, email: str, role: str = "reader", notify: bool = False
) -> dict[str, Any]:
    if role not in VALID_SHARE_ROLES:
        return error(
            f"invalid role {role!r}; must be one of {sorted(VALID_SHARE_ROLES)}"
        )
    svc = _svc()
    body = {"type": "user", "role": role, "emailAddress": email}
    perm = with_retry(
        lambda: svc.permissions()
        .create(
            fileId=file_id,
            body=body,
            sendNotificationEmail=notify,
            fields="id,role,emailAddress",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {"ok": True, "file_id": file_id, **perm}


@tool(
    name="drive_soft_delete",
    feature="drive.write",
    description=(
        "Move a file to the `_delete-later` folder instead of deleting it. "
        "The file is recoverable — revisit the folder in the Drive web UI and "
        "either move items back or empty the folder when you're sure."
    ),
    input_schema={
        "type": "object",
        "required": ["file_id"],
        "properties": {"file_id": {"type": "string"}},
    },
)
def drive_soft_delete(file_id: str) -> dict[str, Any]:
    return drive_common.soft_delete(file_id)
