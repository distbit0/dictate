# Dictate – Voice-to-Text Automation

`voice.py` turns your microphone into a hands-free dictation tool.  
It records audio until you signal it to stop, sends the audio to OpenAI’s
Whisper / GPT-4o transcription API, then **types** the recognised text into the
currently-focused window via `xdotool` (or you can copy the transcript from the
clipboard / log file).

---

## Main Workflow

1. **Start** `python voice.py` (or bind it to a hotkey).
2. Script checks for a lock-file to ensure only one instance runs.
3. A named FIFO `./stop_recording_signal` is created – recording begins.
4. When you want to stop, **write anything** to that pipe, e.g.:

   ```bash
   echo > stop_recording_signal      # or bind this to another hotkey
   ```

5. Audio is saved to `tmp/<timestamp>_<rand>.wav` then (optionally) volume-boosted.
6. File is chunked / trimmed if too long, sent to OpenAI for transcription.
7. The transcript is post-processed, copied to the clipboard and—when
   `type_dictation` is true—typed into the active window with `xdotool`.
8. Old temporary media files are automatically purged (12-hour retention).

Desktop notifications (`notify-send`) announce major steps and errors.

---

## Configuration

All runtime options live in `config.json` **in the project root**:

```json
{
  "max_recording_duration": 300,            // seconds (fallback safety-stop)
  "input_device": "alsa_input.xxx",        // PulseAudio source name or omit
  "type_dictation": true,                   // if true use xdotool to type
  "volume_boost_percent": 40               // extra gain applied to WAV before sending
}
```

•  `input_device` – exact PulseAudio source name.  Leave blank to keep default
   device. You can list sources with `pactl list short sources`.
•  `volume_boost_percent` – applied via *pydub*; helps quiet mics.

### Environment variables

| Variable          | Purpose                          |
|-------------------|----------------------------------|
| `OPENAI_API_KEY`  | Required for transcription calls |
| `openaiApiKey`    | (alternative name)               |

Create a `.env` file or export the vars in your shell.  The project loads them
with `python-dotenv`.

---

## Dependencies

Python packages (see `requirements.txt` or install automatically):

- sounddevice
- pydub   *(requires ffmpeg binaries)*
- numpy
- soundfile
- pulsectl
- openai
- loguru
- python-dotenv
- pymediainfo *(requires libmediainfo)*

System packages (Ubuntu/Debian names):

```bash
sudo apt install ffmpeg xdotool libmediainfo0v5 libmediainfo-dev libsndfile1
```

`notify-send` comes from `libnotify-bin` (usually already present).

---

## Installation

```bash
# 1. Clone
git clone https://github.com/youruser/dictate.git
cd dictate

# 2. Create Python env (recommended)
python -m venv .venv && source .venv/bin/activate

# 3. Install deps
pip install -r requirements.txt

# 4. Add your OpenAI key
echo "OPENAI_API_KEY=sk-..." > .env

# 5. (Optional) adjust config.json
```

---

## Usage Examples

Start recording (bind to a hotkey, e.g. Super+Alt+D):

```bash
python voice.py &
```

Stop recording from another shell / script:

```bash
echo > stop_recording_signal
```

The script will automatically exit after typing/copying the transcript.

If you attempt to launch a second instance while one is running it will detect
the lock-file and show a desktop notification instead of starting.

---

## Internals – Key Functions

| Function | Description |
|----------|-------------|
| `record_until_signal()` | Streams microphone samples into memory until FIFO or duration limit hits. |
| `transcribe_mp3()`      | Splits long files into ~10-minute chunks, calls `processMp3File()` for each and stitches the results into paragraphs. |
| `processMp3File()`      | Sends a single file to OpenAI Audio endpoint (model `gpt-4o-transcribe`). |
| `recognize_and_copy_to_memory()` | Runs volume boost, transcription, then `xdotool type` to inject text. |
| `deleteMp3sOlderThan()` | Cleans `tmp/` to avoid disk bloat. |

Read the well-commented source in `voice.py` for deeper details.

---

## Troubleshooting

•  “ALSA lib … cannot find card” – set a valid `input_device` or omit it.  
•  “Error transcribing …” – check OpenAI key / quota.
•  No text typed – make sure the active window accepts keystrokes and
   `type_dictation` is true.

Enable debug logging by inspecting `app.log` (rotated every 5 kB by Loguru).

---

## License

MIT 
Contributions welcome – open a PR!