import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List
from google import genai
from google.genai import types
from jinja2 import Template

logger = logging.getLogger("clipper")


class CandidateClip:
    def __init__(self, title: str, subject: str, start_time: float, end_time: float, score: int, reason: str):
        self.id = str(uuid.uuid4())
        self.title = title.strip()
        self.subject = subject.strip()
        self.start_time = float(start_time)
        self.end_time = float(end_time)
        self.score = int(score)
        self.reason = reason.strip()

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self, video_id: str) -> Dict[str, Any]:
        return {
            "id": self.id,
            "video_id": video_id,
            "title": self.title,
            "subject": self.subject,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "score": self.score,
            "reason": self.reason,
            "status": "candidate",
        }


def compute_overlap_ratio(clip_a: CandidateClip, clip_b: CandidateClip) -> float:
    intersection = max(0.0, min(clip_a.end_time, clip_b.end_time) - max(clip_a.start_time, clip_b.start_time))
    min_dur = min(clip_a.duration, clip_b.duration)
    if min_dur <= 0:
        return 0.0
    return intersection / min_dur


def parse_gemini_json_response(raw_text: str) -> List[Dict[str, Any]]:
    cleaned = raw_text.strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        cleaned = match.group(0)

    data = json.loads(cleaned)
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("Réponse JSON invalide : 'candidates' n'est pas une liste.")
    return candidates


class SelectionManager:
    def __init__(
        self,
        api_key: str,
        prompt_path: Path = Path("prompts/selection.md"),
        model: str = "gemini-1.5-flash",
        min_duration: float = 120.0,
        max_duration: float = 300.0,
        max_overlap_ratio: float = 0.20,
        max_token_threshold: int = 90000,
        chunk_overlap_tokens: int = 3000,
    ):
        if not api_key:
            raise ValueError("GEMINI_API_KEY non configurée dans le fichier .env.")
        self.client = genai.Client(api_key=api_key)
        self.prompt_template = Template(prompt_path.read_text(encoding="utf-8"))
        self.model = model
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.max_overlap_ratio = max_overlap_ratio
        self.max_token_threshold = max_token_threshold
        self.chunk_overlap_tokens = chunk_overlap_tokens

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text) / 3.5)

    def _format_sentences_to_text(self, sentences: List[Dict[str, Any]]) -> str:
        lines = [f"[{s['start']:.1f}s -> {s['end']:.1f}s] {s['text']}" for s in sentences]
        return "\n".join(lines)

    def _query_gemini(self, transcript_chunk: str) -> List[CandidateClip]:
        rendered_prompt = self.prompt_template.render(
            min_seconds=int(self.min_duration),
            max_seconds=int(self.max_duration),
            min_minutes=int(self.min_duration // 60),
            max_minutes=int(self.max_duration // 60),
            transcript_text=transcript_chunk,
        )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=rendered_prompt,
            config=config,
        )

        raw_candidates = parse_gemini_json_response(response.text)
        valid: List[CandidateClip] = []
        for c in raw_candidates:
            st = float(c["start_time"])
            et = float(c["end_time"])
            dur = et - st
            if self.min_duration <= dur <= self.max_duration:
                valid.append(
                    CandidateClip(
                        title=c.get("title", c.get("subject", "Extrait")),
                        subject=c.get("subject", ""),
                        start_time=st,
                        end_time=et,
                        score=c.get("score", 70),
                        reason=c.get("reason", ""),
                    )
                )
            else:
                logger.warning(f"Clip ignoré (durée {dur:.1f}s hors plage {self.min_duration}-{self.max_duration}s)")
        return valid

    def deduplicate(self, candidates: List[CandidateClip]) -> List[CandidateClip]:
        sorted_clips = sorted(candidates, key=lambda x: x.score, reverse=True)
        retained: List[CandidateClip] = []

        for candidate in sorted_clips:
            conflict = False
            for accepted in retained:
                if compute_overlap_ratio(candidate, accepted) >= self.max_overlap_ratio:
                    conflict = True
                    break
            if not conflict:
                retained.append(candidate)

        retained.sort(key=lambda x: x.start_time)
        return retained[:15]

    def select_clips(self, transcript_data: Dict[str, Any]) -> List[CandidateClip]:
        sentences = transcript_data.get("sentences", [])
        if not sentences:
            return []

        full_text = self._format_sentences_to_text(sentences)
        est_tokens = self._estimate_tokens(full_text)

        candidates: List[CandidateClip] = []

        if est_tokens <= self.max_token_threshold:
            logger.info(f"Envoi transcription complète à Gemini ({est_tokens} tokens estimés)...")
            candidates = self._query_gemini(full_text)
        else:
            logger.info(f"Filet de sécurité activé : transcription longue ({est_tokens} tokens). Découpage en blocs...")
            current_idx = 0
            n = len(sentences)

            while current_idx < n:
                accumulated_text = []
                idx = current_idx
                while idx < n:
                    line = f"[{sentences[idx]['start']:.1f}s -> {sentences[idx]['end']:.1f}s] {sentences[idx]['text']}"
                    accumulated_text.append(line)
                    if self._estimate_tokens("\n".join(accumulated_text)) >= self.max_token_threshold:
                        break
                    idx += 1

                chunk_str = "\n".join(accumulated_text)
                logger.info(f"Traitement du bloc de {sentences[current_idx]['start']}s à {sentences[min(idx, n-1)]['end']}s...")
                chunk_clips = self._query_gemini(chunk_str)
                candidates.extend(chunk_clips)

                if idx >= n:
                    break
                current_idx = max(
                    current_idx + 1,
                    idx - int(len(accumulated_text) * (self.chunk_overlap_tokens / self.max_token_threshold))
                )

        return self.deduplicate(candidates)
