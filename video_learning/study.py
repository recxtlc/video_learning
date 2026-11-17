"""
video-study - turn transcripts into study material with Claude.

Reads the transcripts made by `video-transcript` (one .md per lesson, grouped in
module folders) and, for each module (or each lesson), asks Claude for:

  notes.md         structured notes, summary and key concepts
  flashcards.csv   question/answer cards (imports straight into Anki)
  quiz.md          multiple-choice practice quiz with an answer key
  study_pack.json  the raw data (used by `video-quiz` for interactive practice)

Plus, at the top of the output folder:
  STUDY_GUIDE.md        every module's summary and key concepts in one place
  all_flashcards.csv    every card from the course

Already-processed units are skipped, so you can stop and re-run safely
(use --force to regenerate).

Needs an Anthropic API key in the ANTHROPIC_API_KEY environment variable:
  setx ANTHROPIC_API_KEY "sk-ant-..."     (then open a new terminal)

Usage:
  video-study "C:\\course\\transcripts"
  video-study "C:\\course\\transcripts" --per lesson --cards 10 --questions 5
  video-study "C:\\course\\transcripts" --only "Module 3" --force
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
from pathlib import Path

DEFAULT_MODEL = os.environ.get("VIDEO_STUDY_MODEL", "claude-sonnet-5-5")
COMBINED_NAME = "_ALL_TRANSCRIPTS.md"
MAX_CHARS = 400_000  # ~100k tokens; beyond this, use --per lesson

SYSTEM_PROMPT = """You are an expert tutor turning a video course transcript into study material.

Rules:
- Base everything strictly on the transcript. Do not add facts, tools, numbers or claims it does not contain. If the transcript is vague on something, stay vague rather than filling gaps.
- Write for a working software engineer: clear and direct, no filler, no motivational fluff.
- Notes: organise by concept, not by the order things were said. Use Markdown headings (###) and bullets. Capture definitions, distinctions, processes/steps, examples and pitfalls.
- Flashcards: one idea per card. Fronts are specific questions (not "What is X?" for everything; also ask "why", "how does X differ from Y", "what happens when"). Backs are 1-3 sentences.
- Quiz: test understanding and application, not trivia like lesson numbers. Exactly 4 options each, one clearly correct, three plausible distractors of similar length. Explanations say why the answer is right and why the tempting wrong option is wrong.
- Ignore course housekeeping (e.g. "welcome to module 3", "see you in the next lesson")."""

STUDY_TOOL = {
    "name": "save_study_pack",
    "description": "Save the study material generated from the transcript.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title for this unit"},
            "summary": {"type": "string", "description": "3-5 sentence overview of what this unit teaches"},
            "key_concepts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["term", "explanation"],
                },
            },
            "notes_markdown": {"type": "string", "description": "Structured study notes in Markdown"},
            "flashcards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"front": {"type": "string"}, "back": {"type": "string"}},
                    "required": ["front", "back"],
                },
            },
            "quiz": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 4},
                        "answer_index": {"type": "integer", "minimum": 0, "maximum": 3},
                        "explanation": {"type": "string"},
                    },
                    "required": ["question", "options", "answer_index", "explanation"],
                },
            },
        },
        "required": ["title", "summary", "key_concepts", "notes_markdown", "flashcards", "quiz"],
    },
}


# ---------------------------------------------------------------- discovery

def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def find_units(root: Path, out: Path, per: str) -> list[tuple[str, list[Path]]]:
    """Return [(unit_name, [lesson files])] in course order."""
    if root.is_file():
        return [(root.stem, [root])]
    lessons = sorted(
        (p for p in root.rglob("*.md") if p.name != COMBINED_NAME and out not in p.parents and p.parent != out),
        key=lambda p: natural_key(p.relative_to(root)),
    )
    if per == "lesson":
        return [(str(p.relative_to(root).with_suffix("")), [p]) for p in lessons]
    units: dict[str, list[Path]] = {}
    for p in lessons:
        rel_parent = p.parent.relative_to(root)
        name = str(rel_parent) if str(rel_parent) != "." else root.name
        units.setdefault(name, []).append(p)
    return list(units.items())


def safe_dirname(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', " - ", name).strip(" .")[:120]


# ---------------------------------------------------------------- Claude

def generate_pack(client, model: str, unit: str, text: str, cards: int, questions: int) -> tuple[dict, object]:
    prompt = (
        f"Course unit: {unit}\n\n"
        f"Create study material from the transcript below. Aim for about {cards} flashcards "
        f"and exactly {questions} quiz questions (fewer cards is fine if the content is thin).\n\n"
        f"<transcript>\n{text}\n</transcript>"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[STUDY_TOOL],
        tool_choice={"type": "tool", "name": STUDY_TOOL["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("response was cut off (max_tokens); try --per lesson or fewer --cards/--questions")
    block = next((b for b in msg.content if b.type == "tool_use"), None)
    if block is None:
        raise RuntimeError("Claude did not return study material")
    return block.input, msg.usage


def clean_pack(pack: dict, seed: str) -> dict:
    """Validate quiz items and shuffle options so answers aren't always in the same slot."""
    rng = random.Random(seed)
    quiz = []
    for q in pack.get("quiz", []):
        opts = q.get("options") or []
        idx = q.get("answer_index")
        if len(opts) < 2 or not isinstance(idx, int) or not 0 <= idx < len(opts):
            continue
        correct = opts[idx]
        rng.shuffle(opts)
        quiz.append({**q, "options": opts, "answer_index": opts.index(correct)})
    pack["quiz"] = quiz
    pack["flashcards"] = [c for c in pack.get("flashcards", []) if c.get("front") and c.get("back")]
    return pack


# ---------------------------------------------------------------- writers

LETTERS = "ABCD"


def write_pack(dest: Path, unit: str, sources: list[Path], pack: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "study_pack.json").write_text(
        json.dumps({"unit": unit, "sources": [s.name for s in sources], **pack}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    concepts = "\n".join(f"- **{c['term']}**: {c['explanation']}" for c in pack["key_concepts"])
    (dest / "notes.md").write_text(
        f"# {pack['title']}\n\n_{unit}_\n\n## Summary\n\n{pack['summary']}\n\n"
        f"## Key concepts\n\n{concepts}\n\n## Notes\n\n{pack['notes_markdown'].strip()}\n",
        encoding="utf-8",
    )

    with open(dest / "flashcards.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        for c in pack["flashcards"]:
            w.writerow([c["front"], c["back"], safe_dirname(unit).replace(" ", "_")])

    lines = [f"# Quiz: {pack['title']}\n"]
    for i, q in enumerate(pack["quiz"], 1):
        lines.append(f"**{i}. {q['question']}**\n")
        lines += [f"- {LETTERS[j]}) {o}" for j, o in enumerate(q["options"])]
        lines.append("")
    lines.append("---\n\n## Answers\n")
    for i, q in enumerate(pack["quiz"], 1):
        lines.append(f"{i}. **{LETTERS[q['answer_index']]}**: {q['explanation']}\n")
    (dest / "quiz.md").write_text("\n".join(lines), encoding="utf-8")


def write_course_files(out: Path) -> None:
    packs = sorted(out.rglob("study_pack.json"), key=lambda p: natural_key(p.relative_to(out)))
    guide = ["# Study guide\n"]
    with open(out / "all_flashcards.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        for p in packs:
            data = json.loads(p.read_text(encoding="utf-8"))
            rel = p.parent.relative_to(out).as_posix()
            guide.append(f"## {data['title']}\n\n_{data['unit']}_ · [notes](<{rel}/notes.md>) · [quiz](<{rel}/quiz.md>)\n")
            guide.append(data["summary"] + "\n")
            guide += [f"- **{c['term']}**: {c['explanation']}" for c in data["key_concepts"]]
            guide.append("")
            tag = safe_dirname(data["unit"]).replace(" ", "_")
            for c in data["flashcards"]:
                w.writerow([c["front"], c["back"], tag])
    (out / "STUDY_GUIDE.md").write_text("\n".join(guide), encoding="utf-8")


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(prog="video-study", description="Turn transcripts into notes, flashcards and quizzes with Claude.")
    ap.add_argument("transcripts", type=Path, help="transcripts folder from video-transcript (or a single .md file)")
    ap.add_argument("--out", type=Path, help="output folder (default: <transcripts>/../study)")
    ap.add_argument("--per", choices=["module", "lesson"], default="module", help="one study pack per module (default) or per lesson")
    ap.add_argument("--only", help="only process units whose name contains this text, e.g. \"Module 3\"")
    ap.add_argument("--cards", type=int, default=20, help="target flashcards per unit (default 20)")
    ap.add_argument("--questions", type=int, default=10, help="quiz questions per unit (default 10)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model (default {DEFAULT_MODEL})")
    ap.add_argument("--force", action="store_true", help="regenerate units that already have a study pack")
    ap.add_argument("--dry-run", action="store_true", help="list what would be processed, without calling Claude")
    args = ap.parse_args(argv)

    root = args.transcripts.resolve()
    if not root.exists():
        sys.exit(f"Not found: {root}")
    base = root.parent if root.is_file() else root
    out = (args.out or base.parent / "study").resolve()

    units = find_units(root, out, args.per)
    if args.only:
        units = [u for u in units if args.only.lower() in u[0].lower()]
    if not units:
        sys.exit("No transcript .md files found. Run video-transcript first.")

    todo = [u for u in units if args.force or not (out / safe_dirname(u[0]) / "study_pack.json").exists()]
    print(f"{len(units)} unit(s) found, {len(todo)} to generate -> {out}")
    if args.dry_run:
        for name, files in todo:
            chars = sum(len(f.read_text(encoding='utf-8')) for f in files)
            print(f"  {name}  ({len(files)} file(s), ~{chars // 4:,} tokens)")
        return

    if todo:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit(
                "ANTHROPIC_API_KEY is not set.\n"
                "Create a key at https://console.anthropic.com/ then run:\n"
                '  setx ANTHROPIC_API_KEY "sk-ant-..."\n'
                "and open a new terminal."
            )
        import anthropic

        client = anthropic.Anthropic(max_retries=4)

    total_in = total_out = 0
    failures = 0
    for i, (name, files) in enumerate(todo, 1):
        text = "\n\n".join(f.read_text(encoding="utf-8") for f in files)
        print(f"[{i}/{len(todo)}] {name} ({len(files)} file(s))...", flush=True)
        if len(text) > MAX_CHARS:
            print("  skipped: too long for one request, use --per lesson")
            failures += 1
            continue
        try:
            pack, usage = generate_pack(client, args.model, name, text, args.cards, args.questions)
            pack = clean_pack(pack, seed=name)
            write_pack(out / safe_dirname(name), name, files, pack)
        except Exception as e:  # keep going with the other units
            print(f"  FAILED: {e}")
            failures += 1
            continue
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        print(f"  {len(pack['flashcards'])} cards, {len(pack['quiz'])} questions "
              f"({usage.input_tokens:,} in / {usage.output_tokens:,} out tokens)")

    if any(out.rglob("study_pack.json")):
        write_course_files(out)
    print(f"\nDone. Tokens used: {total_in:,} in / {total_out:,} out.")
    print(f"Start here: {out / 'STUDY_GUIDE.md'}")
    print(f'Practise:   video-quiz "{out}"')
    if failures:
        sys.exit(f"{failures} unit(s) failed; re-run the same command to retry just those.")


if __name__ == "__main__":
    main()
