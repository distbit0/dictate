from __future__ import annotations

import io
import json
import os
import shlex
import subprocess
import threading
import time
import traceback
from os import path
from typing import Tuple

import numpy as np
import sounddevice as sd
import soundfile as sf  # Encodes FLAC into a BytesIO object
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI

load_dotenv()

FIFO_PATH = "./stop_recording_signal"
LOCK_FILE_PATH = "./voice_lock_file"

# -----------------------------------------------------------------------------
# Config + logging helpers
# -----------------------------------------------------------------------------

def get_abs_path(rel: str) -> str:
    return path.abspath(path.join(path.dirname(__file__), rel))


def get_config() -> dict:
    return json.loads(open(get_abs_path("config.json")).read())


def configure_logging() -> None:
    logger.add(
        "app.log",
        rotation="5 KB",
        retention=5,
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )


configure_logging()

# -----------------------------------------------------------------------------
# Notify helper
# -----------------------------------------------------------------------------

def notify_user(msg: str, duration: int = 1) -> None:
    logger.info(msg)
    subprocess.run(["notify-send", msg, "-t", str(duration)])


# -----------------------------------------------------------------------------
# Audio utils
# -----------------------------------------------------------------------------

def normalise_audio(x: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
    peak = np.abs(x).max()
    if peak == 0:
        return x
    return (x * (target_peak / peak)).astype(np.float32)


# -----------------------------------------------------------------------------
# OpenAI client (singleton)
# -----------------------------------------------------------------------------

_client: OpenAI | None = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("openaiApiKey") or os.getenv("OPENAI_API_KEY")
        _client = OpenAI(api_key=api_key)
    return _client


# -----------------------------------------------------------------------------
# Recording routine
# -----------------------------------------------------------------------------

def record_until_signal() -> Tuple[np.ndarray, int]:
    sr = 16_000  # Whisper prefers 16 kHz
    max_dur = get_config()["max_recording_duration"]
    audio_chunks = []
    stop_event = threading.Event()

    def listen_pipe():
        with open(FIFO_PATH, "r") as fifo:
            fifo.read()
        stop_event.set()

    threading.Thread(target=listen_pipe, daemon=True).start()

    def callback(indata, _frames, _time, status):
        if status:
            logger.warning(status)
        audio_chunks.append(indata.copy())

    with sd.InputStream(
        samplerate=sr,
        channels=1,
        blocksize=1024,
        dtype="float32",
        callback=callback,
    ):
        start = time.time()
        while True:
            if stop_event.is_set():
                break
            if not os.path.exists(LOCK_FILE_PATH):
                notify_user("Lock file missing; stopping recorder.")
                break
            if time.time() - start > max_dur:
                notify_user(f"Max duration {max_dur}s reached; stopping.")
                break
            time.sleep(0.1)

    if not audio_chunks:
        raise RuntimeError("No audio captured")
    audio = np.concatenate(audio_chunks).flatten()
    return audio, sr


# -----------------------------------------------------------------------------
# Transcription via OpenAI Whisper servers
# -----------------------------------------------------------------------------

def transcribe(audio: np.ndarray, sr: int) -> str:
    audio = normalise_audio(audio)
    buf = io.BytesIO()
    # Whisper accepts FLAC; we set the filename so the API infers format.
    buf.name = "speech.flac"  # type: ignore[attr-defined]
    sf.write(buf, audio, sr, format="FLAC", subtype="PCM_16")
    buf.seek(0)

    client = get_client()
    resp = client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
        response_format="text",
    )
    return resp.strip()


# -----------------------------------------------------------------------------
# High‑level workflow
# -----------------------------------------------------------------------------

def recognise_and_copy_to_memory():
    # import cProfile, pstats, io as sysio

    # pr = cProfile.Profile()
    # pr.enable()
    # try:
    audio, sr = record_until_signal()
    text = transcribe(audio, sr)
    logger.info(f"Recognised text:\n{text}")

    cmd = [
        "xdotool",
        "type",
        "--delay",
        "7",
        "--clearmodifiers",
        "--",
        text,
    ]
    subprocess.run(cmd, check=True)
    # finally:
    #     pr.disable()
    #     out = sysio.StringIO()
    #     pstats.Stats(pr, stream=out).sort_stats("cumulative").print_stats(20)
    #     logger.info("Profile results:\n{}", out.getvalue())


# -----------------------------------------------------------------------------
# Entrypoint – identical control flow to original script
# -----------------------------------------------------------------------------

def main() -> None:
    if not os.path.exists(FIFO_PATH):
        if os.path.exists(LOCK_FILE_PATH):
            notify_user("Already running (lock file present).")
            return
        os.mkfifo(FIFO_PATH)
    else:
        with open(FIFO_PATH, "w") as fifo:
            fifo.write("stop")
        os.remove(FIFO_PATH)
        return

    open(LOCK_FILE_PATH, "w").write("1")
    notify_user("Starting remote transcription …")

    try:
        recognise_and_copy_to_memory()
    except Exception as e:
        logger.error(f"Fatal error: {e}\n{traceback.format_exc()}")
    finally:
        for p in (LOCK_FILE_PATH, FIFO_PATH):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()