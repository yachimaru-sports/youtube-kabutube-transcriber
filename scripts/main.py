"""Jumping Point!! 株Tube 文字起こし自動収集・Googleドライブ保存 エントリポイント。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drive_uploader import build_drive_service, upload_text_file
from youtube_fetcher import build_output_filename, fetch_channel_videos, get_formatted_transcript

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROCESSED_PATH = ROOT_DIR / "data" / "processed_ids.json"


def setup_logging() -> None:
    """ロギング設定を初期化する。"""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_processed_ids(path: Path) -> list[str]:
    """処理済み動画ID一覧を読み込む。"""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("processed_ids") or [])


def save_processed_ids(path: Path, processed_ids: list[str]) -> None:
    """処理済み動画ID一覧を原子的に保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp.json")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump({"processed_ids": processed_ids}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def run_pipeline(
    channel_id: str,
    processed_path: Path,
    max_videos: int = 15,
    duplicate_policy: str = "skip",
    dry_run: bool = False,
    output_dir: Path | None = None,
) -> int:
    """新着検知〜文字起こし〜Drive保存〜履歴更新のメイン処理を実行する。"""
    logger = logging.getLogger("main")

    processed_list = load_processed_ids(processed_path)
    processed_set = set(processed_list)
    logger.info("処理済み動画IDを %d 件読み込みました。", len(processed_list))

    videos = fetch_channel_videos(channel_id, max_videos=max_videos)
    new_videos = [v for v in videos if v.video_id not in processed_set]

    if not new_videos:
        logger.info("新着の未処理動画はありません。正常終了します。")
        return 0

    logger.info("未処理の新着動画を %d 件検出しました。", len(new_videos))

    drive_service = None
    folder_id = os.getenv("GDRIVE_FOLDER_ID", "").strip()
    if not dry_run:
        sa_json = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
        drive_service = build_drive_service(sa_json)
    else:
        logger.info("DRY_RUN モードのため Googleドライブへのアップロードと履歴更新はスキップします。")

    # 古い順に処理して履歴を積み上げる
    targets = list(reversed(new_videos))

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        save_dir = output_dir if output_dir is not None else Path(tmp_dir_str)
        save_dir.mkdir(parents=True, exist_ok=True)

        for video in targets:
            logger.info("処理開始: %s (%s)", video.title, video.video_id)
            transcript_text = get_formatted_transcript(video)
            if not transcript_text:
                logger.warning("文字起こしを取得できなかったためスキップします: %s", video.video_id)
                continue

            filename = build_output_filename(video.published_yyyymmdd, video.title)
            out_file = save_dir / filename
            out_file.write_text(transcript_text, encoding="utf-8")
            logger.info("テキスト生成完了: %s (%d 文字)", out_file.name, len(transcript_text))

            if not dry_run and drive_service is not None:
                upload_text_file(
                    service=drive_service,
                    file_path=out_file,
                    folder_id=folder_id,
                    duplicate_policy=duplicate_policy,
                )
                processed_list.append(video.video_id)
                processed_set.add(video.video_id)
                save_processed_ids(processed_path, processed_list)
                logger.info("処理済みIDを記録しました: %s", video.video_id)

    return 0


def main() -> None:
    load_dotenv()
    setup_logging()

    parser = argparse.ArgumentParser(description="Jumping Point!! 株Tube 文字起こし自動収集パイプライン")
    parser.add_argument(
        "--channel-id",
        default=os.getenv("YOUTUBE_CHANNEL_ID", "UCgDa6dxD3jPElw6eCvL1T2g"),
        help="対象YouTubeチャンネルID",
    )
    parser.add_argument("--max-videos", type=int, default=15, help="チェックする最新動画数")
    parser.add_argument(
        "--duplicate-policy",
        choices=["skip", "overwrite"],
        default=os.getenv("GDRIVE_DUPLICATE_POLICY", "skip"),
        help="Googleドライブに同名ファイルがある場合の挙動",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("DRY_RUN", "false").lower() == "true",
        help="Googleドライブへのアップロードと processed_ids.json の更新を行わない",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="生成した .txt ファイルをローカルにも残す場合の保存先ディレクトリ",
    )
    args = parser.parse_args()

    exit_code = run_pipeline(
        channel_id=args.channel_id,
        processed_path=DEFAULT_PROCESSED_PATH,
        max_videos=args.max_videos,
        duplicate_policy=args.duplicate_policy,
        dry_run=args.dry_run,
        output_dir=args.output_dir,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
