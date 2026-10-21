import logging
from pathlib import Path
from typing import Any, Dict, List
import yt_dlp

logger = logging.getLogger("clipper")


class IngestionManager:
    def __init__(self, storage_dir: Path):
        self.downloads_dir = storage_dir / "downloads"
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def resolve_url(self, url: str) -> List[Dict[str, Any]]:
        ydl_opts = {
            "extract_flat": "in_playlist",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
        }
        items = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []

            if "entries" in info:
                for entry in info["entries"]:
                    if entry:
                        items.append({
                            "id": entry.get("id"),
                            "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                            "title": entry.get("title", "Sans titre"),
                            "channel_name": entry.get("uploader") or entry.get("channel", "Inconnu"),
                            "duration": float(entry.get("duration") or 0.0),
                        })
            else:
                items.append({
                    "id": info.get("id"),
                    "url": info.get("webpage_url") or url,
                    "title": info.get("title", "Sans titre"),
                    "channel_name": info.get("uploader") or info.get("channel", "Inconnu"),
                    "duration": float(info.get("duration") or 0.0),
                })
        return items

    def download_video(self, video_id: str, url: str) -> Path:
        for ext in ["mp4", "mkv", "webm"]:
            candidate = self.downloads_dir / f"{video_id}.{ext}"
            if candidate.exists() and candidate.stat().st_size > 0:
                logger.info(f"Fichier déjà téléchargé : {candidate}")
                return candidate

        out_template = str(self.downloads_dir / f"{video_id}.%(ext)s")
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": out_template,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }

        logger.info(f"Téléchargement du média source pour {url}...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        final_path = self.downloads_dir / f"{video_id}.mp4"
        if not final_path.exists():
            matches = list(self.downloads_dir.glob(f"{video_id}.*"))
            if matches:
                return matches[0]
            raise FileNotFoundError(f"Échec lors de la finalisation du téléchargement : {video_id}")

        return final_path
