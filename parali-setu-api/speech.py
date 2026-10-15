"""Voice I/O for Parali Setu (PRD docs/PARALI_SETU_PRD.md, Section 8.1 /
12) -- Cloud Speech-to-Text in, Cloud Text-to-Speech out. Both confirmed
live in this project for Hindi (hi-IN) and Punjabi (pa-IN) before this
was wired into main.py, same discipline as everything else so far:
Text-to-Speech was already enabled on ai-builder-cup-aidatlas; Speech-
to-Text was enabled for this project on 2026-10-15 and round-trip
tested (synthesize a known sentence, transcribe it back) in both
languages before any farmer-facing code was written against it.

Like extraction.py, this file only ever turns speech into text or text
into speech -- it never decides a price or quantity.
"""
from __future__ import annotations

import os

from google.cloud import speech, texttospeech

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "ai-builder-cup-aidatlas")

# One confirmed-working Chirp3-HD voice per language (PRD Section 12).
# Chirp3-HD was chosen over Standard/Wavenet after confirming live that
# both hi-IN and pa-IN have broad Chirp3-HD voice catalogs available.
VOICE_BY_LANGUAGE = {
    "Hindi": ("hi-IN", "hi-IN-Chirp3-HD-Achernar"),
    "Punjabi": ("pa-IN", "pa-IN-Chirp3-HD-Achernar"),
}


def transcribe_audio(audio_bytes: bytes, language: str, sample_rate_hertz: int = 16000) -> str | None:
    """PRD 8.1.2 -- farmer's spoken listing to text. Returns None (not an
    exception) on failure, so callers show the confirm/edit text box
    directly rather than erroring the whole flow -- a transcription miss
    is explicitly a handled case, not a crash (Section 13.1)."""
    lang_code, _ = VOICE_BY_LANGUAGE.get(language, ("hi-IN", None))
    client = speech.SpeechClient()
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate_hertz,
        language_code=lang_code,
    )
    audio = speech.RecognitionAudio(content=audio_bytes)
    try:
        response = client.recognize(config=config, audio=audio)
    except Exception:
        return None
    if not response.results:
        return None
    return response.results[0].alternatives[0].transcript


def synthesize_speech(text: str, language: str) -> bytes | None:
    """PRD 8.1.6 -- Gemini's narration text to audio, in the farmer's
    language. Returns None on failure; callers fall back to showing the
    text-only explanation rather than erroring the whole response."""
    lang_code, voice_name = VOICE_BY_LANGUAGE.get(language, ("hi-IN", "hi-IN-Chirp3-HD-Achernar"))
    client = texttospeech.TextToSpeechClient()
    synth_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code=lang_code, name=voice_name)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=16000
    )
    try:
        response = client.synthesize_speech(input=synth_input, voice=voice, audio_config=audio_config)
    except Exception:
        return None
    return response.audio_content
