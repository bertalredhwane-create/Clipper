import json
import logging
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from src.config import load_config
from src.database import Database
from src.ingestion import IngestionManager
from src.transcription import TranscriptionManager
from src.selection import SelectionManager

app = typer.Typer(help="Clipper - Découpe automatique et gratuite de clips YouTube.")
console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@app.command()
def add(url: str):
    """Ajoute une URL (vidéo ou playlist) à la file d'attente Clipper."""
    config, _ = load_config()
    db = Database(config.app.database_path)
    ingestion = IngestionManager(config.app.storage_dir)

    console.print(f"[bold cyan]Inspection de l'URL :[/bold cyan] {url}")
    items = ingestion.resolve_url(url)
    if not items:
        console.print("[red]Aucune vidéo valide n'a pu être résolue.[/red]")
        raise typer.Exit(1)

    added = 0
    for item in items:
        ok = db.insert_video_if_not_exists(
            video_id=item["id"],
            url=item["url"],
            title=item["title"],
            channel_name=item["channel_name"],
            duration=item["duration"],
        )
        if ok:
            added += 1
            console.print(f"  [green]+ Enregistré :[/green] {item['title']} ({item['duration'] // 60:.0f} min)")

    console.print(f"[bold green]Terminé :[/bold green] {added} vidéo(s) ajoutée(s) en file d'attente.")


@app.command()
def run():
    """Exécute l'ingestion yt-dlp, la transcription faster-whisper et la sélection Gemini Flash."""
    config, env = load_config()
    db = Database(config.app.database_path)
    ingestion = IngestionManager(config.app.storage_dir)
    transcription = TranscriptionManager(
        model_name=config.ai.whisper_model,
        device=config.ai.whisper_device,
        compute_type=config.ai.whisper_compute_type,
    )
    selection = SelectionManager(
        api_key=env.gemini_api_key,
        model=config.ai.gemini_model,
        min_duration=config.pipeline.clip_min_duration_seconds,
        max_duration=config.pipeline.clip_max_duration_seconds,
        max_overlap_ratio=config.pipeline.max_overlap_ratio,
        max_token_threshold=config.ai.max_token_threshold,
        chunk_overlap_tokens=config.ai.chunk_overlap_tokens,
    )

    pending = db.get_pending_videos()
    if not pending:
        console.print("[yellow]Aucune vidéo en attente de traitement.[/yellow]")
        return

    console.print(f"[bold cyan]Lancement des travaux pour {len(pending)} vidéo(s)...[/bold cyan]")

    for video in pending:
        v_id = video["id"]
        title = video["title"]
        console.print(f"\n[bold]→ {title} ({v_id})[/bold]")

        try:
            # Ingestion
            file_path = video.get("file_path")
            if not file_path or not Path(file_path).exists():
                console.print("  [blue]Téléchargement source...[/blue]")
                dl_path =
