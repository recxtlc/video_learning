# video-learning

Turn a folder of course videos into transcripts, then turn the transcripts into notes, flashcards and quizzes with Claude, then practise in the terminal.

```
videos ──video-transcript──▶ transcripts/ ──video-study──▶ study/ ──video-quiz──▶ practice
```

## Install (Windows)

Double-click `install.bat`, or run it from a terminal in this folder:

```
install.bat            :: normal install
install.bat whisper    :: also install faster-whisper (for videos with no subtitle file)
```

It runs `pip install -e .`, which uses `setup.py` to create `video-transcript.exe`, `video-study.exe` and `video-quiz.exe`. It also makes sure Python's Scripts folder is on your user PATH, so the commands work in CMD, PowerShell and Windows Terminal. Open a **new** terminal afterwards.

The install is editable (`-e`), so changes you make to the code here take effect immediately with no reinstall. If you move this folder, run `install.bat` again.

Then set your Anthropic API key once (create one at https://console.anthropic.com/):

```
setx ANTHROPIC_API_KEY "sk-ant-..."
```

## Use

```
video-transcript "C:\Videos\Some Course"
video-study      "C:\Videos\Some Course\transcripts"
video-quiz       "C:\Videos\Some Course\study"
```

### video-transcript
For each video, it uses the subtitle file next to it (`.srt` / `.vtt`) if there is one. Otherwise it transcribes the audio locally with Whisper. The output is one Markdown file per lesson, plus `_ALL_TRANSCRIPTS.md`.

| Option | |
|---|---|
| `--out DIR` | output folder (default `<videos>\transcripts`) |
| `--force-whisper` | ignore subtitle files |
| `--whisper-model small` | `tiny` / `base` / `small` / `medium` / `large-v3` |

### video-study
This sends one request to Claude per module and writes a folder per module containing:
`notes.md` · `flashcards.csv` (Anki-importable) · `quiz.md` · `study_pack.json`.
It also writes `STUDY_GUIDE.md` and `all_flashcards.csv` covering the whole course.
Units that are already done are skipped, so re-running only does what's missing.

| Option | |
|---|---|
| `--per lesson` | one pack per lesson instead of per module |
| `--only "Module 3"` | just matching units |
| `--cards 20 --questions 10` | amount per unit |
| `--model NAME` | default `claude-sonnet-5-5` (or set `VIDEO_STUDY_MODEL`) |
| `--force` | regenerate existing packs |
| `--dry-run` | show units and rough token counts, no API calls |

### video-quiz
| | |
|---|---|
| `video-quiz study` | 10 random multiple-choice questions |
| `video-quiz study -n 0 --only "Module 2"` | all questions from Module 2 |
| `video-quiz study --cards` | flashcards: reveal, then mark known / not known |
| `video-quiz study --retry` | only items you got wrong before (kept in `missed.json`) |

## Importing flashcards into Anki
File → Import → `all_flashcards.csv`. The fields are Front, Back and Tags (the module name), separated by commas.

## Troubleshooting
- **`'video-study' is not recognized`**: open a new terminal. If that doesn't fix it, run `python -m video_learning.pathfix`.
- **No subtitle file and Whisper isn't installed**: run `install.bat whisper`.
