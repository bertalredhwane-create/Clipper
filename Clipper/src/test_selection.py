import pytest
from src.selection import CandidateClip, compute_overlap_ratio, parse_gemini_json_response


def test_overlap_ratio():
    c1 = CandidateClip("Titre 1", "Idée 1", 0.0, 100.0, 90, "Excellente intro")
    c2 = CandidateClip("Titre 2", "Idée 2", 85.0, 185.0, 85, "Suite")
    assert pytest.approx(compute_overlap_ratio(c1, c2), 0.01) == 0.15

    c3 = CandidateClip("Titre 3", "Idée 3", 50.0, 150.0, 80, "Recouvrement fort")
    assert pytest.approx(compute_overlap_ratio(c1, c3), 0.01) == 0.50


def test_parse_gemini_json_response():
    sample = """
    {
      "candidates": [
        {
          "title": "Comment l'effet Lindy prédit la survie des technologies",
          "subject": "L'explication concrète de l'effet Lindy",
          "start_time": 150.0,
          "end_time": 320.0,
          "score": 94,
          "reason": "Exemple parlant et chute limpide"
        }
      ]
    }
    """
    res = parse_gemini_json_response(sample)
    assert len(res) == 1
    assert res[0]["title"] == "Comment l'effet Lindy prédit la survie des technologies"
    assert res[0]["score"] == 94
