import sounddevice as sd
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

FIFO_PATH = "./stop_recording_signal"
LOCK_FILE_PATH = "./voice_lock_file"
MAX_RECORDING_DURATION = 120
sys.stdout = open("script_log.txt", "w")
sys.stderr = open("script_error.txt", "w")


def getAbsPath(relPath):
    basepath = path.dirname(__file__)
    return path.abspath(path.join(basepath, relPath))


def getConfig():
    configFileName = getAbsPath("config.json")
    return json.loads(open(configFileName).read())


def notify_user(message, duration=1):
    print(message)
    subprocess.run(["notify-send", message, "-t", str(duration)])


def record_until_signal(samplerate):
    audio_chunks = []
    stop_signal_received = threading.Event()

    def listen_to_pipe():
        with open(FIFO_PATH, "r") as fifo:
            fifo.read()
        stop_signal_received.set()

    threading.Thread(target=listen_to_pipe, daemon=True).start()

    def audio_callback(indata, frames, time, status):
        if status:
            print("WARNING:", status)
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
        if time.time() - start_time > MAX_RECORDING_DURATION:
            notify_user(
                f"Recording exceeded maximum duration of {MAX_RECORDING_DURATION} seconds. Stopping."
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
            prompt=None,
        )
        return api_response.text
    except Exception as e:
        print(f"Error during audio transcription: {e}")
        return ""


def recognize_and_copy_to_memory(audio_filename, apiKey):
    recognized_text = processMp3File(audio_filename, apiKey)
    print(f"Recognized Text:\n{recognized_text}")
    os.system('./ydotoolBin/ydotool type "' + recognized_text + '" --next-delay 0')
    pyperclip.copy(recognized_text)
    subprocess.run(["xclip"], input=recognized_text.encode("utf-8"))


def main():
    if not os.path.exists(FIFO_PATH):
        if os.path.exists(LOCK_FILE_PATH):
            print(f"Lock file {LOCK_FILE_PATH} already exists.")
            notify_user(
                "Already running. Remove the lock file if you want to run another instance. File: "
                + LOCK_FILE_PATH
            )
            exit(0)
        os.mkfifo(FIFO_PATH)
    else:
        print(f"Named pipe {FIFO_PATH} already exists.")
        with open(FIFO_PATH, "w") as fifo:
            fifo.write("stop")
        os.remove(FIFO_PATH)
        exit(0)

    print("Starting... 5")
    if os.path.exists(LOCK_FILE_PATH):
        print(f"Lock file {LOCK_FILE_PATH} already exists.")
        notify_user(
            "Already running. Remove the lock file if you want to run another instance. File: "
            + LOCK_FILE_PATH
        )
        exit(0)

    print(f"Lock file {LOCK_FILE_PATH} does not exist. Creating...")
    lock_file = open(LOCK_FILE_PATH, "w")
    lock_file.write("1")
    lock_file.close()
    print(f"Lock file {LOCK_FILE_PATH} created.")

    apiKey = os.environ.get("OPENAI_API_KEY")

    try:
        notify_user("Starting transcription...")
        audio_filename = "recording.wav"
        samplerate = 48000
        audio_data = record_until_signal(samplerate)
        save_audio(audio_filename, audio_data, samplerate)
        print(f"Audio saved as {audio_filename}. Size: {len(audio_data) * 2} bytes.")
        recognize_and_copy_to_memory(audio_filename, apiKey)
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        os.remove(LOCK_FILE_PATH)
        try:
            os.remove(FIFO_PATH)
        except:
            pass


if __name__ == "__main__":
    main()
