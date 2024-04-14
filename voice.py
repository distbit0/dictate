import sounddevice as sd
import pulsectl
from openai import OpenAI
import numpy as np
import subprocess
import pyperclip
import soundfile
import os
import threading
import sys
import time
from os import path
import json
from loguru import logger


def configure_logging():
    logger.add(
        "app.log",
        rotation="30 KB",
        retention=5,
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )


configure_logging()

FIFO_PATH = "./stop_recording_signal"
LOCK_FILE_PATH = "./voice_lock_file"


def set_input_device(device_name):
    with pulsectl.Pulse("my-client-name") as pulse:
        for source in pulse.source_list():
            if source.name == device_name:
                pulse.default_set(source)
                print("Input device set to:", device_name)
                break


def getAbsPath(relPath):
    basepath = path.dirname(__file__)
    return path.abspath(path.join(basepath, relPath))


def getConfig():
    configFileName = getAbsPath("config.json")
    return json.loads(open(configFileName).read())


def notify_user(message, duration=1):
    logger.info(message)
    subprocess.run(["notify-send", message, "-t", str(duration)])


def record_until_signal(samplerate):
    audio_chunks = []
    stop_signal_received = threading.Event()
    max_recording_duration = getConfig()["max_recording_duration"]

    def listen_to_pipe():
        with open(FIFO_PATH, "r") as fifo:
            fifo.read()
        stop_signal_received.set()

    threading.Thread(target=listen_to_pipe, daemon=True).start()

    def audio_callback(indata, frames, time, status):
        if status:
            logger.info("WARNING:", status)
        audio_chunks.append(indata.copy())

    stream = sd.InputStream(
        samplerate=samplerate,
        channels=1,
        blocksize=256,
        callback=audio_callback,
    )
    stream.start()

    start_time = time.time()
    about_to_stop = False
    while about_to_stop is False:
        if not os.path.exists(LOCK_FILE_PATH):
            notify_user("Lock file not found. Exiting.")
            about_to_stop = True
        if not os.path.exists(FIFO_PATH):
            about_to_stop = True
        if stop_signal_received.is_set():
            about_to_stop = True
        if time.time() - start_time > max_recording_duration:
            notify_user(
                f"Recording exceeded maximum duration of {max_recording_duration} seconds. Stopping."
            )
            about_to_stop = True
        time.sleep(0.25)  # Add a small delay to reduce CPU usage
    stream.stop()
    stream.close()
    return np.concatenate(audio_chunks)[:, 0]


def save_audio(filename, recordedAudio, samplerate):
    soundfile.write(filename, recordedAudio, samplerate, format="wav")


def processMp3File(mp3FileName, apiKey):
    client = OpenAI(api_key=apiKey)
    try:
        api_response = client.audio.transcriptions.create(
            model="whisper-1",
            file=open(mp3FileName, "rb"),
            language="en",
            prompt="My idea is the following: ",
        )
        return api_response.text
    except Exception as e:
        logger.info(f"Error during audio transcription: {e}")
        return ""


def recognize_and_copy_to_memory(audio_filename, apiKey):
    recognized_text = processMp3File(audio_filename, apiKey)
    logger.info(f"Recognized Text:\n{recognized_text}")
    if getConfig()["type_dictation"]:
        os.system(
            "echo -e 'typedelay 0\ntypehold 0\ntype " + recognized_text + "' | dotool"
        )

    if getConfig()["copy_dictation"]:
        pyperclip.copy(recognized_text)
        subprocess.run(["xclip"], input=recognized_text.encode("utf-8"))


def main():
    if not os.path.exists(FIFO_PATH):
        if os.path.exists(LOCK_FILE_PATH):
            logger.info(f"Lock file {LOCK_FILE_PATH} already exists.")
            notify_user(
                "Already running. Remove the lock file if you want to run another instance. File: "
                + LOCK_FILE_PATH
            )
            exit(0)
        os.mkfifo(FIFO_PATH)
    else:
        logger.info(f"Named pipe {FIFO_PATH} already exists.")
        with open(FIFO_PATH, "w") as fifo:
            fifo.write("stop")
        os.remove(FIFO_PATH)
        exit(0)

    logger.info("Starting... 5")
    if os.path.exists(LOCK_FILE_PATH):
        logger.info(f"Lock file {LOCK_FILE_PATH} already exists.")
        notify_user(
            "Already running. Remove the lock file if you want to run another instance. File: "
            + LOCK_FILE_PATH
        )
        exit(0)

    logger.info(f"Lock file {LOCK_FILE_PATH} does not exist. Creating...")
    lock_file = open(LOCK_FILE_PATH, "w")
    lock_file.write("1")
    lock_file.close()
    logger.info(f"Lock file {LOCK_FILE_PATH} created.")

    apiKey = os.environ.get("OPENAI_API_KEY")

    try:
        notify_user("Starting transcription...")
        if "input_device" in getConfig():
            logger.info(f"Input device set to: {getConfig()['input_device']}")
            set_input_device(getConfig()["input_device"])
        audio_filename = "recording.wav"
        samplerate = 48000
        audio_data = record_until_signal(samplerate)
        save_audio(audio_filename, audio_data, samplerate)
        logger.info(
            f"Audio saved as {audio_filename}. Size: {len(audio_data) * 2} bytes."
        )
        recognize_and_copy_to_memory(audio_filename, apiKey)
    except Exception as e:
        logger.info(f"An error occurred: {e}")
    finally:
        os.remove(LOCK_FILE_PATH)
        try:
            os.remove(FIFO_PATH)
        except:
            pass


if __name__ == "__main__":
    main()
