"""Google Drive API を用いたファイルアップロードモジュール。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]


def build_drive_service(service_account_json: str) -> Any:
    """サービスアカウントJSON（文字列またはファイルパス）からDrive APIクライアントを生成する。"""
    raw = service_account_json.strip()
    if not raw:
        raise ValueError("GDRIVE_SERVICE_ACCOUNT_JSON が設定されていません。")

    if raw.startswith("{"):
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
    else:
        json_path = Path(raw)
        if not json_path.exists():
            raise FileNotFoundError(f"サービスアカウントJSONファイルが見つかりません: {json_path}")
        creds = service_account.Credentials.from_service_account_file(str(json_path), scopes=DRIVE_SCOPES)

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_existing_file_id(service: Any, filename: str, folder_id: str) -> str | None:
    """指定フォルダ内の同名ファイルIDを検索する。存在しない場合は None を返す。"""
    escaped_name = filename.replace("\\", "\\\\").replace("'", "\\'")
    query = f"name = '{escaped_name}' and '{folder_id}' in parents and trashed = false"
    res = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = res.get("files") or []
    return files[0]["id"] if files else None


def upload_text_file(
    service: Any,
    file_path: Path,
    folder_id: str,
    duplicate_policy: str = "skip",
) -> dict[str, str]:
    """テキストファイルをGoogleドライブの指定フォルダへアップロードする。

    Args:
        service: Drive API サービスオブジェクト
        file_path: アップロードするローカル `.txt` ファイルパス
        folder_id: Googleドライブの保存先フォルダID
        duplicate_policy: 同名ファイル存在時の挙動（"skip" または "overwrite"）
    """
    if not folder_id:
        raise ValueError("GDRIVE_FOLDER_ID が設定されていません。")

    filename = file_path.name
    existing_id = find_existing_file_id(service, filename, folder_id)

    if existing_id and duplicate_policy == "skip":
        logger.info("同名ファイルが既に存在するためスキップしました: %s (id=%s)", filename, existing_id)
        return {"status": "skipped", "file_id": existing_id, "name": filename}

    media = MediaFileUpload(str(file_path), mimetype="text/plain", resumable=False)

    if existing_id and duplicate_policy == "overwrite":
        updated = (
            service.files()
            .update(
                fileId=existing_id,
                media_body=media,
                fields="id, name",
                supportsAllDrives=True,
            )
            .execute()
        )
        logger.info("既存ファイルを上書きアップロードしました: %s (id=%s)", updated["name"], updated["id"])
        return {"status": "overwritten", "file_id": updated["id"], "name": updated["name"]}

    metadata = {"name": filename, "parents": [folder_id]}
    created = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id, name",
            supportsAllDrives=True,
        )
        .execute()
    )
    logger.info("新規アップロード完了: %s (id=%s)", created["name"], created["id"])
    return {"status": "created", "file_id": created["id"], "name": created["name"]}
