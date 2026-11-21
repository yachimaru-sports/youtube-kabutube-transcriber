"""YouTube新着動画検知・字幕取得・テキストフォーマット整形モジュール。"""

from __future__ import annotations

import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


@dataclass
class VideoInfo:
    """検知したYouTube動画のメタ情報。"""

    video_id: str
    title: str
    published_yyyymmdd: str
    url: str


def sanitize_filename(name: str, max_len: int = 120) -> str:
    """Windows/Linux/Googleドライブで安全なファイル名へサニタイズする。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" ._")
    return cleaned or "untitled"


def build_output_filename(published_yyyymmdd: str, title: str) -> str:
    """`YYYYMMDD_<動画タイトル>.txt` 形式のファイル名を生成する。"""
    safe_date = published_yyyymmdd if re.fullmatch(r"\d{8}", published_yyyymmdd) else datetime.now(JST).strftime("%Y%m%d")
    safe_title = sanitize_filename(title)
    return f"{safe_date}_{safe_title}.txt"


def to_jst_yyyymmdd(published_raw: str | None) -> str:
    """ISO8601日時文字列またはYYYYMMDD文字列をJSTのYYYYMMDDに変換する。"""
    if not published_raw:
        return datetime.now(JST).strftime("%Y%m%d")
    s = str(published_raw).strip()
    if re.fullmatch(r"\d{8}", s):
        return s
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JST).strftime("%Y%m%d")
    except ValueError:
        return datetime.now(JST).strftime("%Y%m%d")


def fetch_channel_videos_via_rss(channel_id: str, max_videos: int = 15) -> list[VideoInfo]:
    """YouTube公式RSSフィードからチャンネルの最新動画一覧を取得する。"""
    url = RSS_URL_TEMPLATE.format(channel_id=channel_id)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        xml_bytes = resp.read()

    root = ET.fromstring(xml_bytes)
    videos: list[VideoInfo] = []
    for entry in root.findall("atom:entry", ATOM_NS)[:max_videos]:
        vid_el = entry.find("yt:videoId", ATOM_NS)
        title_el = entry.find("atom:title", ATOM_NS)
        pub_el = entry.find("atom:published", ATOM_NS)
        if vid_el is None or not vid_el.text:
            continue
        vid = vid_el.text.strip()
        title = title_el.text.strip() if (title_el is not None and title_el.text) else f"動画_{vid}"
        pub_raw = pub_el.text.strip() if (pub_el is not None and pub_el.text) else None
        videos.append(
            VideoInfo(
                video_id=vid,
                title=title,
                published_yyyymmdd=to_jst_yyyymmdd(pub_raw),
                url=f"https://www.youtube.com/watch?v={vid}",
            )
        )
    return videos


def fetch_channel_videos_via_ytdlp(channel_id: str, max_videos: int = 15) -> list[VideoInfo]:
    """yt-dlp を用いてチャンネルの最新動画一覧を取得する（RSS失敗時のフォールバック）。"""
    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
    ydl_opts = {
        "extract_flat": True,
        "playlistend": max_videos,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    entries = (info or {}).get("entries") or []
    videos: list[VideoInfo] = []
    for entry in entries[:max_videos]:
        if not entry or not entry.get("id"):
            continue
        vid = entry["id"]
        videos.append(
            VideoInfo(
                video_id=vid,
                title=entry.get("title") or f"動画_{vid}",
                published_yyyymmdd=to_jst_yyyymmdd(entry.get("upload_date")),
                url=f"https://www.youtube.com/watch?v={vid}",
            )
        )
    return videos


def fetch_channel_videos(channel_id: str, max_videos: int = 15) -> list[VideoInfo]:
    """チャンネルの最新動画一覧を取得する（RSS優先、失敗時はyt-dlpにフォールバック）。"""
    try:
        videos = fetch_channel_videos_via_rss(channel_id, max_videos=max_videos)
        if videos:
            return videos
    except Exception as exc:
        logger.warning("RSSフィード取得に失敗したため yt-dlp にフォールバックします: %s", exc)
    return fetch_channel_videos_via_ytdlp(channel_id, max_videos=max_videos)


def format_segment_line(start_seconds: float, text: str) -> str:
    """1セグメントを `<M:SS><M 分 S 秒><テキスト>` 形式に整形する。"""
    total_sec = max(0, int(start_seconds))
    hours, rem = divmod(total_sec, 3600)
    mins, secs = divmod(rem, 60)
    if hours > 0:
        clock_str = f"{hours}:{mins:02d}:{secs:02d}"
        jp_str = f"{hours} 時間 {mins} 分 {secs} 秒"
    elif mins > 0:
        clock_str = f"{mins}:{secs:02d}"
        jp_str = f"{mins} 分 {secs} 秒"
    else:
        clock_str = f"0:{secs:02d}"
        jp_str = f"{secs} 秒"

    cleaned_text = re.sub(r"\s+", " ", text).strip()
    return f"{clock_str}{jp_str}{cleaned_text}"


def format_transcript_segments(segments: list[dict[str, Any]]) -> str:
    """セグメント一覧を規定フォーマットのテキスト本文へ変換する。"""
    lines: list[str] = []
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        start = float(seg.get("start", 0.0))
        lines.append(format_segment_line(start, text))
    return "\n\n".join(lines) + ("\n" if lines else "")


def fetch_youtube_subtitles(video_id: str) -> list[dict[str, Any]] | None:
    """YouTubeの手動日本語字幕または自動生成日本語字幕を取得する。"""
    api = YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
    except Exception as exc:
        logger.warning("YouTube字幕リスト取得失敗 (%s): %s", video_id, exc)
        return None

    target = None
    for finder in (
        lambda: transcript_list.find_manually_created_transcript(["ja", "ja-JP"]),
        lambda: transcript_list.find_generated_transcript(["ja", "ja-JP"]),
    ):
        try:
            target = finder()
            break
        except Exception:
            continue

    if target is None:
        return None

    try:
        fetched = target.fetch()
        segments: list[dict[str, Any]] = []
        for item in fetched:
            text = getattr(item, "text", None)
            start = getattr(item, "start", 0.0)
            if text is None and isinstance(item, dict):
                text = item.get("text", "")
                start = item.get("start", 0.0)
            cleaned = str(text).replace("\n", " ").strip()
            if cleaned:
                segments.append({"start": float(start), "text": cleaned})
        return segments or None
    except Exception as exc:
        logger.warning("YouTube字幕フェッチ失敗 (%s): %s", video_id, exc)
        return None


def transcribe_audio_fallback(video_id: str, video_url: str) -> list[dict[str, Any]] | None:
    """字幕が取得できない場合の音声文字起こしフォールバック（拡張ポイント）。

    必要に応じて yt-dlp での音声ダウンロード + Whisper / 外部ASR API 呼び出しを
    ここに実装・差し替えできます。戻り値は [{"start": float, "text": str}, ...] です。
    """
    logger.info(
        "字幕が取得できなかったため音声フォールバックポイントに到達しました (%s: %s)。",
        video_id,
        video_url,
    )
    return None


def get_formatted_transcript(video: VideoInfo) -> str | None:
    """動画の文字起こしを取得し、規定フォーマットの文字列として返す。"""
    segments = fetch_youtube_subtitles(video.video_id)
    if not segments:
        segments = transcribe_audio_fallback(video.video_id, video.url)
    if not segments:
        return None
    formatted = format_transcript_segments(segments)
    return formatted if formatted.strip() else None
