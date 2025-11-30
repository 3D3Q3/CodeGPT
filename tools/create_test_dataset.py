"""Create repeatable test directories and files for library_scanner.

The script builds two directories under the repository root:
- ``test_data/library_source``: nested folders with representative document
  types, zero-byte files, media files, hidden/temp/partial names, and duplicates.
- ``test_data/library_destination``: empty destination directory for copy tests.

Running the script will delete and recreate both locations so tests start clean.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent / "test_data"
SOURCE_DIR = BASE_DIR / "library_source"
DEST_DIR = BASE_DIR / "library_destination"

CATEGORIES = [
    "Mathematics",
    "Physics",
    "Computer Programming",
    "Machine Learning",
    "Cookbooks",
    "History",
    "Biology",
    "Chemistry",
    "Philosophy",
    "Art",
]

TARGET_FILES: Iterable[Tuple[str, str, str]] = [
    ("Mathematics", "algebra_notes.pdf", "Linear algebra overview"),
    ("Physics", "quantum_readings.epub", "Quantum basics placeholder"),
    ("Computer Programming", "python_patterns.docx", "Design patterns summary"),
    ("Machine Learning", "neural_networks.doc", "Intro to neural nets"),
    ("Cookbooks", "vegan_recipes.txt", "Plant-based recipes"),
    ("History", "renaissance_art.mobi", "Renaissance art notes"),
    ("Biology", "cell_biology.azw", "Cell structure"),
    ("Chemistry", "organic_chemistry.azw3", "Organic chemistry primer"),
    ("Philosophy", "stoicism.rtf", "Stoic philosophy"),
    ("Art", "modern_art.md", "Modern art movements"),
]

# Problematic or non-target files to exercise filters and edge cases.
EDGE_CASE_FILES: Iterable[Tuple[str, str, str | None]] = [
    ("Mathematics", "empty_notes.pdf", None),  # zero-byte target file
    ("Physics", "draft.tmp", "Temporary draft"),  # temp suffix
    ("Machine Learning", "dataset.part1.pdf", "Partial download"),  # name contains 'part'
    ("Cookbooks", ".hidden_recipe.pdf", "Hidden file"),  # hidden file
    ("History", "lecture_video.mp4", "Video file should be skipped"),
    ("Biology", "podcast_episode.mp3", "Audio file should be skipped"),
    ("Chemistry", "notes.txt~", "Backup suffix should be skipped"),
    ("Philosophy", "diagram.png", "Non-target extension"),
]

# Duplicate content to verify deduplication (same name and size in two locations).
DUPLICATE_FILES: Iterable[Tuple[str, str, str]] = [
    ("Mathematics", "duplicate_source.pdf", "Duplicate content"),
    ("Mathematics/Archive", "duplicate_source.pdf", "Duplicate content"),
]

# Nested paths to exercise recursion.
NESTED_TARGETS: Iterable[Tuple[str, str, str]] = [
    ("Computer Programming/Books", "systems_programming.epub", "Systems overview"),
    ("Machine Learning/Deep", "cnn_research.pdf", "CNN research"),
]


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        path.touch()
    else:
        path.write_text(content, encoding="utf-8")


def populate_files() -> None:
    for category in CATEGORIES:
        (SOURCE_DIR / category).mkdir(parents=True, exist_ok=True)

    for category, filename, content in TARGET_FILES:
        write_file(SOURCE_DIR / category / filename, content)

    for relative_dir, filename, content in EDGE_CASE_FILES:
        write_file(SOURCE_DIR / relative_dir / filename, content)

    for relative_dir, filename, content in DUPLICATE_FILES:
        write_file(SOURCE_DIR / relative_dir / filename, content)

    for relative_dir, filename, content in NESTED_TARGETS:
        write_file(SOURCE_DIR / relative_dir / filename, content)

    # Extra uppercase extension to validate normalization.
    write_file(SOURCE_DIR / "Cookbooks" / "baking_GUIDE.TXT", "Uppercase extension")


def summarize_created_files() -> None:
    created = sorted(SOURCE_DIR.rglob("*"))
    print("Created test dataset at:", SOURCE_DIR)
    print("Destination directory:", DEST_DIR)
    for item in created:
        if item.is_dir():
            continue
        size = item.stat().st_size
        print(f"- {item.relative_to(SOURCE_DIR)} ({size} bytes)")


def main() -> None:
    reset_directory(SOURCE_DIR)
    reset_directory(DEST_DIR)
    populate_files()
    summarize_created_files()


if __name__ == "__main__":
    main()
