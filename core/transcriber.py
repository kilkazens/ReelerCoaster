"""
Whisper Speech-to-Text & Word-level Timestamping Module for ReelerCoaster.
"""

import os
import torch
from typing import List, Dict, Any, Optional

_WHISPER_MODEL = None
_CURRENT_MODEL_SIZE = None


def get_device() -> str:
    """Detect best available device (cuda or cpu)."""
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_whisper_model(model_size: str = "base"):
    """Loads and caches the Whisper model in VRAM/RAM."""
    global _WHISPER_MODEL, _CURRENT_MODEL_SIZE
    import whisper

    device = get_device()
    if _WHISPER_MODEL is None or _CURRENT_MODEL_SIZE != model_size:
        print(f"[Transcriber] Loading Whisper model '{model_size}' on {device.upper()}...")
        _WHISPER_MODEL = whisper.load_model(model_size, device=device)
        _CURRENT_MODEL_SIZE = model_size
        print(f"[Transcriber] Model '{model_size}' ready.")
    return _WHISPER_MODEL


def transcribe_clip_audio(
    wav_path: str,
    language: Optional[str] = None,
    model_size: str = "base"
) -> List[Dict[str, Any]]:
    """
    Transcribes the audio file and extracts word-level timestamps.
    Returns a list of word dicts: [{'word': '...', 'start': 0.1, 'end': 0.4}, ...]
    """
    model = load_whisper_model(model_size)
    
    options = {
        "word_timestamps": True,
        "verbose": False,
        "task": "transcribe"
    }
    if language:
        options["language"] = language

    result = model.transcribe(str(wav_path), **options)
    
    words_list: List[Dict[str, Any]] = []
    
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            word_str = w.get("word", "").strip()
            if not word_str:
                continue
            words_list.append({
                "word": word_str,
                "start": float(w.get("start", 0.0)),
                "end": float(w.get("end", 0.0))
            })

    return words_list
