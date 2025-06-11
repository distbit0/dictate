# Dictate: Voice-to-Text Transcription Tool

This script provides a voice dictation service for Linux. It records audio from your microphone, transcribes it using OpenAI's Whisper API, copies the resulting text to your clipboard, and can optionally type it out where your cursor is focused.

## Features

-   **Live Audio Recording:** Captures audio directly from the microphone.
-   **Signal-Based Control:** Start recording by running the script. Stop recording by running the script a second time.
-   **OpenAI Whisper Transcription:** Utilizes the `whisper-1` model for accurate speech-to-text.
-   **Audio Processing:** Includes volume boosting for clearer audio and chunking for large recordings.
-   **Clipboard Integration:** Automatically copies the transcribed text to the system clipboard (`xclip`).
-   **Optional Typing:** Can simulate keyboard input to type out the transcript using `dotool`.
-   **Configuration:** Customizable through a `config.json` file and environment variables.
-   **Desktop Notifications:** Provides feedback using `notify-send`.
-   **Logging:** Detailed logging to `app.log` using `loguru`.
-   **Singleton Instance:** Uses a lock file to prevent multiple recording sessions from running simultaneously.

## Dependencies

### Python Libraries

-   `sounddevice`: For audio recording.
-   `pydub`: For audio manipulation (volume adjustment, chunking). Requires `ffmpeg`.
-   `pulsectl`: For PulseAudio control (setting input device).
-   `openai`: For interacting with the OpenAI API.
-   `numpy`: For numerical audio data.
-   `soundfile`: For saving audio files.
-   `python-dotenv`: For managing environment variables (like API keys).
-   `loguru`: For advanced logging.

It's recommended to install these using a `requirements.txt` file:
```bash
pip install sounddevice pydub pulsectl openai numpy soundfile python-dotenv loguru
```

### System Tools

-   **`ffmpeg`**: Required by `pydub` for audio processing, especially MP3 handling.
    ```bash
    # On Fedora
    sudo dnf install ffmpeg
    # On Debian/Ubuntu
    sudo apt install ffmpeg
    ```
-   **`xclip`**: For copying text to the clipboard.
    ```bash
    # On Fedora
    sudo dnf install xclip
    # On Debian/Ubuntu
    sudo apt install xclip
    ```
-   **`notify-send`**: For desktop notifications (usually pre-installed with desktop environments).
-   **`dotool`**: (Optional) For typing out the transcribed text.

## Setup and Configuration

1.  **Clone the repository or download `voice.py`**.

2.  **Install Python dependencies** (see above).

3.  **Install system tools** (see above).

4.  **OpenAI API Key:**
    Create a `.env` file in the same directory as `voice.py` with your OpenAI API key:
    ```env
    OPENAI_API_KEY=your_openai_api_key_here
    ```

5.  **Configuration File (`config.json`):**
    Create a `config.json` file in the same directory as `voice.py`. This file is relative to the script's location.
    Example `config.json`:
    ```json
    {
        "input_device": "alsa_input.pci-0000_00_1f.3.analog-stereo",
        "volume_boost_percent": 20,
        "max_recording_duration": 1800, 
        "type_dictation": true
    }
    ```
    -   `input_device` (string, optional): The name of your PulseAudio input device (e.g., microphone). Find your device name using `pactl list sources short`.
    -   `volume_boost_percent` (integer): Percentage to boost the audio volume before transcription.
    -   `max_recording_duration` (integer): Maximum recording time in seconds (e.g., 1800 for 30 minutes).
    -   `type_dictation` (boolean): If `true`, the script will use `dotool` to type the transcribed text.

6.  **Temporary Files Directory:**
    The script will create a `tmp/` directory relative to its own location for storing temporary audio files.

## Usage

1.  **Navigate to the script's directory:**
    ```bash
    cd /path/to/script_directory/
    ```
2.  **To start recording:**
    ```bash
    python voice.py
    ```
    A notification "Starting transcription..." will appear. A lock file (`voice_lock_file`) and a named pipe (`stop_recording_signal`) will be created in the current working directory.

3.  **To stop recording:**
    Open a new terminal (or run in the background) in the same directory and execute:
    ```bash
    python voice.py
    ```
    This sends a signal to the recording instance. The recording will stop, process the audio, and the transcript will be copied to your clipboard. If `type_dictation` is true, it will also be typed out.

    Alternatively, recording also stops if:
    - The `max_recording_duration` is reached.
    - The `voice_lock_file` or `stop_recording_signal` pipe is manually deleted (not recommended as primary stop method).

## Logging

Logs are written to `app.log` in the same directory as the script. This file rotates and is retained for a limited number of versions.

## Installing `dotool` (Optional)

`dotool` is used to simulate keyboard input for typing out the dictated text. If you want to use this feature, install `dotool`:

### Installing `dotool` on Fedora

1.  **Enable the Copr repository:**
    ```bash
    sudo dnf copr enable smallcms/dotool -y
    ```

2.  **Install `dotool`:**
    ```bash
    sudo dnf install dotool -y
    ```

3.  **Reload udev rules and trigger events:**
    ```bash
    sudo udevadm control --reload && sudo udevadm trigger
    ```

4.  **Enable and start the `dotoold` service for your user:**
    ```bash
    systemctl --user --now enable dotoold.service
    ```

(For other distributions, please refer to `dotool`'s official installation instructions.)
