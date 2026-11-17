#!/usr/bin/env python3
"""
video-transcript - turn a folder of videos into clean, readable transcripts.

For every video in the folder (searched recursively):
  1. If a subtitle file sits next to it (.srt or .vtt, e.g. "Lesson 1.en_US.srt"),
     it is converted into clean paragraphs. This is instant and needs no extra installs.
  2. Otherwise the audio is transcribed locally with faster-whisper (optional install:
     pip install faster-whisper).

Output (default: <folder>/transcripts/):
  - one Markdown file per video, mirroring the folder structure
  - _ALL_TRANSCRIPTS.md with the whole course in order (handy to upload to Claude)

Usage:
  video-transcript "C:\\path\\to\\course"
  video-transcript "C:\\path\\to\\course" --out "C:\\notes" --whisper-model small
  video-transcript "C:\\path\\to\\course" --force-whisper   # ignore subtitle files
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
SUB_EXTS = {".srt", ".vtt"}
PARAGRAPH_SECONDS = 60  # start a new timestamped paragraph roughly every minute

TIME_RE = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]*\}")


def natural_key(p: Path):
    """Sort '2 - Module' before '10 - Module'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def to_seconds(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_subtitles(path: Path) -> list[tuple[float, str]]:
    """Parse SRT or WebVTT into (start_seconds, text) cues."""
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    cues: list[tuple[float, str]] = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [l.strip() for l in block.strip().splitlines()]
        idx = next((i for i, l in enumerate(lines) if TIME_RE.search(l)), None)
        if idx is None:
            continue  # header, NOTE, STYLE blocks etc.
        start = to_seconds(*TIME_RE.search(lines[idx]).groups()[:4])
        text = " ".join(lines[idx + 1:])
        text = html.unescape(TAG_RE.sub("", text)).strip()
        if text:
            cues.append((start, text))
    # Drop consecutive duplicates (common in auto-generated captions)
    deduped: list[tuple[float, str]] = []
    for start, text in cues:
        if not deduped or deduped[-1][1] != text:
            deduped.append((start, text))
    return deduped


def transcribe_with_whisper(video: Path, model_name: str) -> list[tuple[float, str]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit(
            f"\n'{video.name}' has no subtitle file, so it needs speech-to-text.\n"
            "Install it with:  pip install faster-whisper\n"
        )
    global _MODEL
    if "_MODEL" not in globals():
        print(f"  loading whisper model '{model_name}' (first run downloads it)...")
        _MODEL = WhisperModel(model_name, device="auto", compute_type="int8")
    segments, _ = _MODEL.transcribe(str(video), vad_filter=True)
    return [(seg.start, seg.text.strip()) for seg in segments if seg.text.strip()]


def cues_to_paragraphs(cues: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """Merge short cues into paragraphs that break at a sentence end ~every minute."""
    paras: list[tuple[float, str]] = []
    cur_start, cur_text = None, []
    for start, text in cues:
        if cur_start is None:
            cur_start = start
        cur_text.append(text)
        ends_sentence = text.rstrip().endswith((".", "?", "!"))
        if ends_sentence and start - cur_start >= PARAGRAPH_SECONDS:
            paras.append((cur_start, " ".join(cur_text)))
            cur_start, cur_text = None, []
    if cur_text:
        paras.append((cur_start, " ".join(cur_text)))
    return [(s, re.sub(r"\s+", " ", t)) for s, t in paras]


def find_subtitle(video: Path) -> Path | None:
    """Match 'Lesson 1.mp4' with 'Lesson 1.srt', 'Lesson 1.en_US.srt', 'Lesson 1.en.vtt'..."""
    candidates = [
        p for p in video.parent.iterdir()
        if p.suffix.lower() in SUB_EXTS and (p.stem == video.stem or p.name.startswith(video.stem + "."))
    ]
    # Prefer English if several languages exist
    candidates.sort(key=lambda p: (".en" not in p.name.lower(), p.name))
    return candidates[0] if candidates else None


def main() -> None:
    ap = argparse.ArgumentParser(prog="video-transcript", description="Turn a folder of videos into transcripts.")
    ap.add_argument("folder", type=Path, help="folder containing the videos (searched recursively)")
    ap.add_argument("--out", type=Path, help="output folder (default: <folder>/transcripts)")
    ap.add_argument("--force-whisper", action="store_true", help="ignore subtitle files, always transcribe audio")
    ap.add_argument("--whisper-model", default="small", help="tiny / base / small / medium / large-v3 (default: small)")
    args = ap.parse_args()

    root: Path = args.folder.resolve()
    out: Path = (args.out or root / "transcripts").resolve()
    videos = sorted(
        (p for p in root.rglob("*") if p.suffix.lower() in VIDEO_EXTS and out not in p.parents),
        key=lambda p: natural_key(p.relative_to(root)),
    )
    if not videos:
        sys.exit(f"No videos found in {root}")

    combined = [f"# {root.name} - full transcript\n"]
    current_section = None
    for i, video in enumerate(videos, 1):
        rel = video.relative_to(root)
        sub = None if args.force_whisper else find_subtitle(video)
        source = f"subtitles ({sub.name})" if sub else f"whisper ({args.whisper_model})"
        print(f"[{i}/{len(videos)}] {rel}  <- {source}")

        cues = parse_subtitles(sub) if sub else transcribe_with_whisper(video, args.whisper_model)
        paras = cues_to_paragraphs(cues)
        body = "\n\n".join(f"**[{fmt_ts(s)}]** {t}" for s, t in paras)

        dest = out / rel.with_suffix(".md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f"# {video.stem}\n\n_Source: {rel}_\n\n{body}\n", encoding="utf-8")

        section = str(rel.parent) if str(rel.parent) != "." else None
        if section and section != current_section:
            combined.append(f"\n## {section}\n")
            current_section = section
        combined.append(f"\n### {video.stem}\n\n{body}\n")

    (out / "_ALL_TRANSCRIPTS.md").write_text("\n".join(combined), encoding="utf-8")
    print(f"\nDone: {len(videos)} transcripts in {out}")
    print(f"Combined file: {out / '_ALL_TRANSCRIPTS.md'}")


if __name__ == "__main__":
    main()
