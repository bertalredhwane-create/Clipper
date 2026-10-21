import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
import ctranslate2
from faster_whisper import WhisperModel

logger = logging.getLogger("clipper")


class TranscriptionManager:
    def __init__(
        self,
        model_name: str = "medium",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.compute_type = self._resolve_compute_type(compute_type, self.device)
        self._model: WhisperModel | None = None

    def _resolve_device(self, req_device: str) -> str:
        if req_device != "auto":
            return req_device
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"

    def _resolve_compute_type(self, req_compute: str, device: str) -> str:
        if req_compute != "auto":
            return req_compute
        return "float16" if device == "cuda" else "int8"

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            logger.info(f"Chargement du modèle faster-whisper '{self.model_name}' (device={self.device}, compute={self.compute_type})...")
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def _extract_audio_16k(self, video_path: Path) -> Path:
        audio_path = video_path.with_suffix(".wav")
        if audio_path.exists() and audio_path.stat().st_size > 0:
            return audio_path

        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return audio_path

    def transcribe(self, video_path: Path) -> Tuple[Dict[str, Any], int, float]:
        start_t = time.time()
        audio_file = self._extract_audio_16k(video_path)
        model = self._get_model()

        logger.info(f"Transcription en cours de {audio_file.name}...")
        segments_gen, info = model.transcribe(
            str(audio_file),
            language="fr",
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        all_words:
