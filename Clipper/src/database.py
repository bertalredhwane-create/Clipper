import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    channel_name TEXT,
                    duration REAL NOT NULL,
                    file_path TEXT,
                    status TEXT NOT NULL,
                    transcription_time_seconds REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS transcripts (
                    video_id TEXT PRIMARY KEY,
                    raw_json TEXT NOT NULL,
                    word_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS clips (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    score INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
                );
                """
            )

    def insert_video_if_not_exists(self, video_id: str, url: str, title: str, channel_name: str, duration: float) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO videos (id, url, title, channel_name, duration, status)
                VALUES (?, ?, ?, ?, ?, 'queued')
                """,
                (video_id, url, title, channel_name, duration),
            )
            return cur.rowcount > 0

    def update_video_downloaded(self, video_id: str, file_path: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE videos SET file_path = ?, status = 'downloaded', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (file_path, video_id),
            )

    def update_video_transcription(self, video_id: str, raw_json: str, word_count: int, duration_sec: float) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO transcripts (video_id, raw_json, word_count) VALUES (?, ?, ?)",
                (video_id, raw_json, word_count),
            )
            conn.execute(
                """
                UPDATE videos 
                SET transcription_time_seconds = ?, status = 'transcribed', updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
                """,
                (duration_sec, video_id),
            )

    def mark_video_selected(self, video_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE videos SET status = 'selected', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (video_id,),
            )

    def mark_video_failed(self, video_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE videos SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (video_id,),
            )

    def insert_clips(self, clips: List[Dict[str, Any]]) -> None:
        with self._get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO clips (id, video_id, title, subject, start_time, end_time, score, reason, status)
                VALUES (:id, :video_id, :title, :subject, :start_time, :end_time, :score, :reason, :status)
                """,
                clips,
            )

    def get_pending_videos(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM videos WHERE status != 'selected' AND status != 'failed' ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_videos(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM videos ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_transcript(self, video_id: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT raw_json FROM transcripts WHERE video_id = ?", (video_id,)).fetchone()
            return row["raw_json"] if row else None

    def count_clips_for_video(self, video_id: str) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM clips WHERE video_id = ?", (video_id,)).fetchone()
            return int(row["count"]) if row
