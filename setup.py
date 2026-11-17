from pathlib import Path

from setuptools import find_packages, setup

here = Path(__file__).parent

setup(
    name="video-learning",
    version="0.1.0",
    description="Turn course videos into transcripts, then into notes, flashcards and quizzes with Claude.",
    long_description=(here / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="Alex Nkosi",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "anthropic>=0.40",
    ],
    extras_require={
        # only needed for videos that have no subtitle file
        "whisper": ["faster-whisper>=1.0"],
    },
    # Each entry becomes a real .exe in Python's Scripts folder, so the commands
    # run directly in CMD / PowerShell / Windows Terminal - no "python script.py".
    entry_points={
        "console_scripts": [
            "video-transcript=video_learning.transcribe:main",
            "video-study=video_learning.study:main",
            "video-quiz=video_learning.quiz:main",
            "video-learning-fix-path=video_learning.pathfix:main",
        ],
    },
)
