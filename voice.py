import sounddevice as sd
import shlex
import traceback
import random
from pydub import AudioSegment
from math import ceil
import pulsectl
from openai import OpenAI
import numpy as np
import subprocess
import pyperclip
import re
import soundfile
import os
import threading
import time
from os import path
import json
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


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


def record_until_signal():
    randomNumber = (
        str(int(time.time())) + "_" + str(random.randint(1000000000, 9999999999))
    )
    file_name = getAbsPath(f"{randomNumber}.wav")
    samplerate = 48000
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
    audio_data = np.concatenate(audio_chunks)[:, 0]
    save_audio(file_name, audio_data, samplerate)
    return file_name


def save_audio(filename, recordedAudio, samplerate):
    soundfile.write(filename, recordedAudio, samplerate, format="wav")


def deleteMp3sOlderThan(maxAgeSeconds, output_dir):
    files = os.listdir(output_dir)
    for file in files:
        if file.split(".")[-1] in ["mp3", "webm", "part", "mp4", "txt"]:
            filePath = os.path.join(output_dir, file)
            fileName = filePath.split("/")[-1].split(".")[0]
            if fileName.count("_") == 3:
                creationTime = int(fileName.split("_")[0])
            else:
                creationTime = os.path.getctime(filePath)
            if time.time() - creationTime > maxAgeSeconds:
                print("deleting file", filePath)
                os.remove(filePath)


def chunk_mp3(mp3_file):
    max_size_mb = 0.8
    print(mp3_file)
    randomNumber = mp3_file.split("/")[-1].split(".")[0]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "tmp")
    # Load the MP3 file using pydub
    audio = AudioSegment.from_mp3(mp3_file)

    # Calculate the number of chunks based on the maximum size
    chunk_size_bytes = max_size_mb * 1024 * 1024
    total_chunks = ceil(len(audio) / chunk_size_bytes)

    # Split the audio into chunks
    cumDurOfChunks = 0
    file_paths = []
    for i in range(total_chunks):
        start_time = i * chunk_size_bytes
        end_time = min((i + 1) * chunk_size_bytes, len(audio))
        chunk = audio[start_time:end_time]
        chunk_file = os.path.join(output_dir, f"{randomNumber}_chunk_{i+1}.mp3")
        cumDurOfChunks += len(chunk) / 1000
        chunk.export(chunk_file, format="mp3")
        file_paths.append(chunk_file)

    os.remove(mp3_file)

    return file_paths


def transcribe_mp3(audio_chunks):
    apiKey = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=apiKey)
    markdown_transcript = ""
    for i, chunk_filename in enumerate(audio_chunks):
        print("transcribing chunk", i + 1, "of", len(audio_chunks))
        with open(chunk_filename, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-1",
                language="en",
                response_format="text",
                prompt=(
                    "Continuation of audio (might begin mid-sentence): "
                    if i > 0
                    else "Welcome to this technical episode. "
                ),
            )
        transcript = transcript[:-1] if transcript[-1] == "." else transcript
        markdown_transcript += " " + transcript + "."

    markdown_transcript = re.sub(
        r"((?:[^.!?]+[.!?]\s){4})", r"\1\n\n", markdown_transcript
    )  # split on every 4th sentence
    markdown_transcript = "\n".join(
        [
            line.strip(". ") if not line.strip(". ") else line
            for line in markdown_transcript.split("\n")
        ]
    ).strip()

    # Delete all the temporary mp3 files
    for file in audio_chunks:
        os.remove(file)
    deleteMp3sOlderThan(60 * 60 * 12, getAbsPath("tmp/"))

    return markdown_transcript


def processMp3File(mp3FileName):
    try:
        audio_chunks = chunk_mp3(mp3FileName)
        markdown_transcript = transcribe_mp3(audio_chunks)
        return markdown_transcript
    except Exception as e:
        error = traceback.format_exc()
        logger.info(f"Error during audio transcription: {e} {error}")
        return ""


def recognize_and_copy_to_memory(audio_filename):
    recognized_text = processMp3File(audio_filename).strip()
    logger.info(f"Recognized Text:\n{recognized_text}")
    if getConfig()["type_dictation"]:
        textForDoTool = recognized_text.replace("\n", "")  # "\nkey enter\ntype ")
        command = (
            "echo -e 'typedelay 0\ntypehold 0\nkeydelay 50\nkeyhold 50\ntype "
            + shlex.quote(textForDoTool)[1:-1]
            + "' | dotool"
        )
        os.system(command)

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

    try:
        notify_user("Starting transcription...")
        if "input_device" in getConfig():
            logger.info(f"Input device set to: {getConfig()['input_device']}")
            set_input_device(getConfig()["input_device"])
        audio_filename = record_until_signal()
        logger.info(f"Audio saved as {audio_filename}")
        recognize_and_copy_to_memory(audio_filename)
    except Exception as e:
        error = traceback.format_exc()
        logger.info(f"An error occurred: {e} {error}")
    finally:
        os.remove(LOCK_FILE_PATH)
        try:
            os.remove(FIFO_PATH)
        except:
            pass


if __name__ == "__main__":
    main()
