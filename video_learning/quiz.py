"""
video-quiz - practise in the terminal with the material made by `video-study`.

  video-quiz "C:\\course\\study"                  10 random quiz questions from the whole course
  video-quiz "C:\\course\\study" --only "Module 3" -n 20
  video-quiz "C:\\course\\study" --cards          flip through flashcards instead
  video-quiz "C:\\course\\study" --retry          only questions/cards you got wrong before

Wrong answers are remembered in <study folder>/missed.json so --retry can drill them.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import textwrap
from pathlib import Path

LETTERS = "abcd"


def load(path: Path, only: str | None) -> tuple[list[dict], list[dict]]:
    files = [path] if path.is_file() else sorted(path.rglob("study_pack.json"))
    questions, cards = [], []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if only and only.lower() not in data["unit"].lower():
            continue
        questions += [{**q, "unit": data["unit"]} for q in data.get("quiz", [])]
        cards += [{**c, "unit": data["unit"]} for c in data.get("flashcards", [])]
    return questions, cards


def wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(text, width=90, initial_indent=indent, subsequent_indent=indent)


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nStopped.")
        raise SystemExit(0)


def run_quiz(items: list[dict]) -> tuple[list[str], list[str]]:
    answered, missed, score = [], [], 0
    for i, q in enumerate(items, 1):
        print(f"\n--- Question {i}/{len(items)}  ({q['unit']})")
        print(wrap(q["question"]))
        for j, opt in enumerate(q["options"]):
            print(wrap(f"{LETTERS[j]}) {opt}", "  "))
        valid = LETTERS[: len(q["options"])]
        ans = ""
        while ans not in valid:
            ans = ask(f"Your answer [{'/'.join(valid)}, q to quit]: ")
            if ans == "q":
                return finish(score, answered, missed)
        correct = LETTERS[q["answer_index"]]
        answered.append(q["question"])
        if ans == correct:
            score += 1
            print("Correct.")
        else:
            print(f"Not quite. The answer is {correct}).")
            missed.append(q["question"])
        print(wrap(q["explanation"], "  "))
    return finish(score, answered, missed)


def finish(score: int, answered: list[str], missed: list[str]) -> tuple[list[str], list[str]]:
    if answered:
        print(f"\nScore: {score}/{len(answered)} ({score * 100 // len(answered)}%)")
    return answered, missed


def run_cards(items: list[dict]) -> tuple[list[str], list[str]]:
    answered, missed = [], []
    for i, c in enumerate(items, 1):
        print(f"\n--- Card {i}/{len(items)}  ({c['unit']})")
        print(wrap(c["front"]))
        if ask("[Enter] to reveal, q to quit: ") == "q":
            break
        print(wrap(c["back"], "  "))
        answered.append(c["front"])
        if ask("Did you know it? [y/n]: ").startswith("n"):
            missed.append(c["front"])
    print(f"\n{len(missed)} card(s) to review again.")
    return answered, missed


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(prog="video-quiz", description="Practise with quizzes and flashcards made by video-study.")
    ap.add_argument("study", type=Path, help="study folder from video-study (or one study_pack.json)")
    ap.add_argument("--cards", action="store_true", help="flashcards instead of multiple choice")
    ap.add_argument("--only", help="only units whose name contains this text, e.g. \"Module 3\"")
    ap.add_argument("-n", "--number", type=int, default=10, help="how many to ask (default 10, 0 = all)")
    ap.add_argument("--retry", action="store_true", help="only items you got wrong in earlier sessions")
    ap.add_argument("--in-order", action="store_true", help="don't shuffle")
    args = ap.parse_args(argv)

    path = args.study.resolve()
    if not path.exists():
        sys.exit(f"Not found: {path}")
    questions, cards = load(path, args.only)
    items, key, kind = (cards, "front", "cards") if args.cards else (questions, "question", "questions")

    missed_file = (path if path.is_dir() else path.parent) / "missed.json"
    missed_store = json.loads(missed_file.read_text(encoding="utf-8")) if missed_file.exists() else {}
    previously = set(missed_store.get(kind, []))
    if args.retry:
        items = [it for it in items if it[key] in previously]
    if not items:
        sys.exit("Nothing to practise." + (" No missed items left - nice." if args.retry else " Run video-study first."))

    if not args.in_order:
        random.shuffle(items)
    if args.number:
        items = items[: args.number]

    answered, missed_now = run_cards(items) if args.cards else run_quiz(items)

    # Items answered correctly drop off the missed list; new misses are added.
    answered_ok = set(answered) - set(missed_now)
    missed_store[kind] = sorted((previously - answered_ok) | set(missed_now))
    missed_file.write_text(json.dumps(missed_store, indent=2, ensure_ascii=False), encoding="utf-8")
    if missed_store[kind]:
        print(f"{len(missed_store[kind])} {kind} on your retry list (use --retry).")


if __name__ == "__main__":
    main()
