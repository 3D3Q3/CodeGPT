"""CLI tool for scanning and exporting library-style document inventories.

Usage examples:
    python library_scanner.py /path/to/library \
        --include-ext .pdf .epub \
        --output-json scan.json --output-text scan.txt

Key behaviors:
- Dry-run by default. The tool prints planned outputs and requires explicit
  confirmation before any filesystem writes. Use ``--apply`` (optionally with
  ``--yes`` for non-interactive runs) to persist results.
- Prompts for a copy destination up front and offers a staged, per-category
  copy workflow that always previews actions before copying files into
  category-named folders at the destination.
- Adds an in-between organization stage that lets you rename, remove, and
  move items between categories (no filesystem writes) before any copy step.
- Recursively walks the provided root directory while skipping zero-byte files,
  names containing "part", temporary/hidden files, and non-target media types
  such as audio or video.
- Normalizes and deduplicates matches using case-insensitive paths and a
  name/size fingerprint to avoid repeats.
- Produces two structured views: a concise categorized list by inferred type
  and a detailed list with absolute paths and metadata.
- Supports exporting results to JSON or structured text for downstream tools
  (e.g., LLM ingestion pipelines).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set


TARGET_EXTENSIONS: Set[str] = {
    ".pdf",
    ".epub",
    ".docx",
    ".doc",
    ".txt",
    ".mobi",
    ".azw",
    ".azw3",
    ".rtf",
    ".md",
}
VIDEO_EXTENSIONS: Set[str] = {".mp4", ".mkv", ".avi", ".mov", ".wmv"}
AUDIO_EXTENSIONS: Set[str] = {".mp3", ".flac", ".aac", ".ogg", ".wav"}
TEMP_SUFFIXES: Set[str] = {"~", ".tmp", ".temp"}


@dataclass
class FileRecord:
    path: str
    name: str
    size: int
    extension: str
    category: str

    def to_dict(self) -> Dict[str, str | int]:
        return asdict(self)


def infer_category(extension: str) -> str:
    if extension in {".pdf"}:
        return "pdf"
    if extension in {".epub", ".mobi", ".azw", ".azw3"}:
        return "ebook"
    if extension in {".doc", ".docx", ".rtf"}:
        return "document"
    if extension in {".txt", ".md"}:
        return "text"
    return extension.lstrip(".") or "other"


def should_skip(name: str, extension: str) -> bool:
    lower_name = name.lower()
    if lower_name.startswith("."):
        return True
    if "part" in lower_name:
        return True
    if any(lower_name.endswith(suffix) for suffix in TEMP_SUFFIXES):
        return True
    if extension in VIDEO_EXTENSIONS or extension in AUDIO_EXTENSIONS:
        return True
    return False


def collect_candidates(
    root: Path,
    include_ext: Set[str] | None,
    exclude_ext: Set[str],
    skip_media: bool = True,
) -> List[FileRecord]:
    records: List[FileRecord] = []
    include = {ext.lower() for ext in include_ext} if include_ext else None
    exclude = {ext.lower() for ext in exclude_ext}

    for current_root, dirs, files in os.walk(root):
        # Skip hidden directories early to avoid unnecessary traversal
        dirs[:] = [d for d in dirs if not d.startswith(".") and "part" not in d.lower()]

        for filename in files:
            extension = Path(filename).suffix.lower()
            if should_skip(filename, extension):
                continue
            if skip_media and (extension in VIDEO_EXTENSIONS or extension in AUDIO_EXTENSIONS):
                continue

            normalized_ext = extension
            if include is not None and normalized_ext not in include:
                continue
            if include is None and normalized_ext not in TARGET_EXTENSIONS:
                continue
            if normalized_ext in exclude:
                continue

            absolute_path = Path(current_root, filename)
            try:
                size = absolute_path.stat().st_size
            except OSError:
                continue
            if size == 0:
                continue

            record = FileRecord(
                path=str(absolute_path.resolve()),
                name=absolute_path.name,
                size=size,
                extension=normalized_ext,
                category=infer_category(normalized_ext),
            )
            records.append(record)
    return records


def deduplicate(records: Iterable[FileRecord]) -> List[FileRecord]:
    seen_paths: Set[str] = set()
    name_size_keys: Set[tuple[str, int]] = set()
    deduped: List[FileRecord] = []

    for record in records:
        path_key = record.path.lower()
        name_size_key = (record.name.lower(), record.size)
        if path_key in seen_paths:
            continue
        if name_size_key in name_size_keys:
            continue
        seen_paths.add(path_key)
        name_size_keys.add(name_size_key)
        deduped.append(record)
    return deduped


def build_summary(records: Sequence[FileRecord]) -> Dict[str, List[str]]:
    summary: Dict[str, List[str]] = {}
    for record in records:
        summary.setdefault(record.category, []).append(record.name)
    for names in summary.values():
        names.sort()
    return dict(sorted(summary.items()))


def format_text_output(summary: Dict[str, List[str]], records: Sequence[FileRecord]) -> str:
    lines: List[str] = []
    total = len(records)
    lines.append(f"Total files: {total}")
    lines.append("\nSummary by category:")
    for category, names in summary.items():
        lines.append(f"- {category} ({len(names)}):")
        for name in names:
            lines.append(f"  • {name}")

    lines.append("\nDetailed files:")
    for record in records:
        lines.append(
            f"- {record.category}: {record.name} [{record.extension}] ({record.size} bytes)\n  {record.path}"
        )
    return "\n".join(lines)


def group_by_category(records: Sequence[FileRecord]) -> Dict[str, List[FileRecord]]:
    grouped: Dict[str, List[FileRecord]] = {}
    for record in records:
        grouped.setdefault(record.category, []).append(record)
    return dict(sorted(grouped.items()))


def print_category_table(records: Sequence[FileRecord]) -> None:
    grouped = group_by_category(records)
    print("\nCurrent categories and entries:")
    for category, items in grouped.items():
        print(f"- {category} ({len(items)} files)")
        for idx, record in enumerate(items, start=1):
            print(f"  [{idx}] {record.name}")


def prompt_string(message: str) -> str:
    try:
        return input(message).strip()
    except EOFError:
        return ""


def confirm_action(message: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return prompt_confirmation(message)


def organize_categories(records: Sequence[FileRecord], assume_yes: bool) -> List[FileRecord]:
    editable = list(records)
    if not editable:
        return editable

    print("\nReview stage: reorganize categories before any copying.")
    print("You can rename categories, remove entries, move entries between categories, or delete categories.")

    while True:
        print_category_table(editable)
        print(
            "\nOptions:\n"
            "  1) Rename a category\n"
            "  2) Remove an entire category\n"
            "  3) Move a single entry to another category\n"
            "  4) Remove a single entry\n"
            "  5) Finish organization"
        )
        choice = prompt_string("Select an option [1-5]: ")

        if choice == "1":
            current = prompt_string("Enter the category to rename: ")
            if current not in {r.category for r in editable}:
                print("  Category not found.")
                continue
            new_name = prompt_string("Enter the new category name: ")
            if not new_name:
                print("  No name provided.")
                continue
            if not confirm_action(f"Rename category '{current}' to '{new_name}'?", assume_yes):
                print("  Rename cancelled.")
                continue
            for record in editable:
                if record.category == current:
                    record.category = new_name
            print(f"  Renamed '{current}' to '{new_name}'.")

        elif choice == "2":
            target = prompt_string("Enter the category to remove: ")
            if target not in {r.category for r in editable}:
                print("  Category not found.")
                continue
            if not confirm_action(f"Remove category '{target}' and all its entries?", assume_yes):
                print("  Removal cancelled.")
                continue
            editable = [r for r in editable if r.category != target]
            print(f"  Removed category '{target}'.")

        elif choice == "3":
            category = prompt_string("Enter the category of the entry to move: ")
            grouped = group_by_category(editable)
            if category not in grouped:
                print("  Category not found.")
                continue
            try:
                index = int(prompt_string("Enter the entry number to move (see table): "))
            except ValueError:
                print("  Invalid number.")
                continue
            items = grouped[category]
            if not (1 <= index <= len(items)):
                print("  Entry number out of range.")
                continue
            record = items[index - 1]
            new_category = prompt_string("Enter the destination category name: ")
            if not new_category:
                print("  No destination provided.")
                continue
            message = (
                f"Move '{record.name}' from '{category}' to '{new_category}'?"
            )
            if not confirm_action(message, assume_yes):
                print("  Move cancelled.")
                continue
            record.category = new_category
            print(f"  Moved '{record.name}' to '{new_category}'.")

        elif choice == "4":
            category = prompt_string("Enter the category of the entry to remove: ")
            grouped = group_by_category(editable)
            if category not in grouped:
                print("  Category not found.")
                continue
            try:
                index = int(prompt_string("Enter the entry number to remove (see table): "))
            except ValueError:
                print("  Invalid number.")
                continue
            items = grouped[category]
            if not (1 <= index <= len(items)):
                print("  Entry number out of range.")
                continue
            record = items[index - 1]
            if not confirm_action(f"Remove '{record.name}' from the list?", assume_yes):
                print("  Removal cancelled.")
                continue
            editable.remove(record)
            print(f"  Removed '{record.name}'.")

        elif choice == "5":
            if not confirm_action("Finish organization and lock in the current list?", assume_yes):
                print("  Continuing review stage.")
                continue
            print("  Organization complete. Proceeding to copy stage inputs.")
            break
        else:
            print("  Invalid option. Please choose 1-5.")

    return editable


def prompt_confirmation(message: str) -> bool:
    try:
        response = input(f"{message} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return response in {"y", "yes"}


def export_results(
    records: Sequence[FileRecord],
    json_path: Path | None,
    text_path: Path | None,
    apply_changes: bool,
    assume_yes: bool,
) -> None:
    summary = build_summary(records)
    preview_message = [
        "Planned outputs:",
        f"- JSON: {json_path if json_path else 'none'}",
        f"- Text: {text_path if text_path else 'none'}",
        f"Total records: {len(records)}",
        "\nPreview (concise and detailed):",
        format_text_output(summary, records),
    ]
    print("\n".join(preview_message))

    if not apply_changes:
        print("Dry-run mode: no files were written. Re-run with --apply to export.")
        return

    if not assume_yes and not prompt_confirmation("Proceed with writing output files?"):
        print("Aborted. No files were written.")
        return

    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "summary": summary,
                    "files": [record.to_dict() for record in records],
                },
                f,
                indent=2,
            )
        print(f"Wrote JSON results to {json_path}")

    if text_path:
        text_path.parent.mkdir(parents=True, exist_ok=True)
        with text_path.open("w", encoding="utf-8") as f:
            f.write(format_text_output(summary, records))
        print(f"Wrote text results to {text_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan and export document library metadata.")
    parser.add_argument("root", type=Path, help="Root directory to scan")
    parser.add_argument(
        "--include-ext",
        nargs="*",
        default=None,
        help="Extensions to include (e.g., .pdf .epub). Overrides default target list.",
    )
    parser.add_argument(
        "--exclude-ext",
        nargs="*",
        default=[],
        help="Extensions to exclude (case-insensitive).",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Path to write JSON results (requires --apply).",
    )
    parser.add_argument(
        "--output-text",
        type=Path,
        help="Path to write structured text results (requires --apply).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write outputs instead of previewing (still prompts for confirmation).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts when used with --apply.",
    )
    parser.add_argument(
        "--allow-media",
        action="store_true",
        help="Include audio/video files instead of skipping them.",
    )
    parser.add_argument(
        "--copy-dest",
        type=Path,
        help="Optional destination for staged category copies (prompts before copying).",
    )
    parser.add_argument(
        "--copy-log",
        type=Path,
        help="Path for copy log file (defaults to copy destination / copy_log.txt).",
    )
    return parser.parse_args()


def prompt_for_copy_destination(provided: Path | None) -> Path | None:
    if provided:
        return provided
    try:
        response = input(
            "Optional: enter a copy destination directory for staged category copies (leave blank to skip): "
        ).strip()
    except EOFError:
        return None
    if not response:
        return None
    return Path(response).expanduser()


def ensure_directory(path: Path, assume_yes: bool) -> bool:
    if path.exists():
        if not path.is_dir():
            print(f"Error: copy destination exists but is not a directory: {path}")
            return False
        return True
    if not assume_yes and not prompt_confirmation(
        f"Create copy destination directory? {path}"
    ):
        print("Copy destination not created; skipping copy workflow.")
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def dry_run_category_copy(category: str, records: Sequence[FileRecord], copy_dest: Path) -> None:
    dest_dir = copy_dest / category
    print(f"\nDry run for category '{category}' -> {dest_dir}")
    if not records:
        print("  No files to copy.")
        return
    for record in records:
        destination = dest_dir / record.name
        print(f"  PLAN: copy {record.path} -> {destination}")


def write_copy_log(log_path: Path, entries: List[str]) -> None:
    if not entries:
        return
    timestamp = datetime.utcnow().isoformat() + "Z"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n# Copy session {timestamp}\n")
        for line in entries:
            log_file.write(line + "\n")


def execute_category_copy(
    category: str,
    records: Sequence[FileRecord],
    copy_dest: Path,
    log_path: Path,
) -> None:
    dest_dir = copy_dest / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    log_entries: List[str] = []
    for record in records:
        source_path = Path(record.path)
        destination = dest_dir / record.name
        if destination.exists():
            print(f"  SKIP: destination already exists, leaving untouched -> {destination}")
            log_entries.append(f"SKIP existing {destination} (source {source_path})")
            continue
        try:
            shutil.copy2(source_path, destination)
            print(f"  COPIED: {source_path} -> {destination}")
            log_entries.append(f"COPIED {source_path} -> {destination}")
        except OSError as exc:
            print(f"  ERROR: failed to copy {source_path} -> {destination}: {exc}")
            log_entries.append(f"ERROR {source_path} -> {destination}: {exc}")
    write_copy_log(log_path, log_entries)


def staged_copy_workflow(
    records: Sequence[FileRecord],
    copy_dest: Path | None,
    assume_yes: bool,
    log_path: Path | None,
) -> None:
    if not records:
        return
    if copy_dest is None:
        print("No copy destination provided. Skipping copy workflow.")
        return
    dest = copy_dest
    if not ensure_directory(dest, assume_yes=assume_yes):
        return

    log_file = log_path or dest / "copy_log.txt"
    grouped = group_by_category(records)
    print("\nStaged copy workflow ready.")
    print(f"Destination: {dest}")
    print(f"Log file: {log_file}")
    print("Categories to consider (counts):")
    for category, items in grouped.items():
        print(f"  - {category}: {len(items)}")

    if not assume_yes and not prompt_confirmation(
        "Begin step-by-step copy of categories? This will always prompt before copying."
    ):
        print("Copy workflow skipped by user.")
        return

    for category, items in grouped.items():
        print(f"\nCategory: {category} ({len(items)} files)")
        if not assume_yes and not prompt_confirmation(
            f"Handle category '{category}' with a dry run?"
        ):
            print("  Skipped.")
            continue
        dry_run_category_copy(category, items, dest)

        if not assume_yes and not prompt_confirmation(
            f"Proceed to copy category '{category}' to {dest}?"
        ):
            print("  Copy skipped after dry run.")
            continue
        execute_category_copy(category, items, dest, log_file)
        print(f"  Completed copying category '{category}'.")


def main() -> None:
    args = parse_args()

    copy_destination = prompt_for_copy_destination(args.copy_dest)

    if not args.root.exists():
        print(f"Error: root path does not exist: {args.root}")
        return
    if not args.root.is_dir():
        print(f"Error: root path is not a directory: {args.root}")
        return

    include_ext = set(args.include_ext) if args.include_ext else None
    exclude_ext = set(args.exclude_ext)

    records = collect_candidates(
        root=args.root,
        include_ext=include_ext,
        exclude_ext=exclude_ext,
        skip_media=not args.allow_media,
    )
    deduped_records = deduplicate(records)

    print(f"Discovered {len(records)} candidates; {len(deduped_records)} after deduplication.")
    if not deduped_records:
        print("No matching files found.")

    export_results(
        records=deduped_records,
        json_path=args.output_json,
        text_path=args.output_text,
        apply_changes=args.apply,
        assume_yes=args.yes,
    )

    organized_records = deduped_records
    if deduped_records:
        if confirm_action(
            "Enter category organization stage before copying?", assume_yes=args.yes
        ):
            organized_records = organize_categories(deduped_records, assume_yes=args.yes)
        else:
            print("Skipping organization stage; using current categories as-is.")

    staged_copy_workflow(
        records=organized_records,
        copy_dest=copy_destination,
        assume_yes=args.yes,
        log_path=args.copy_log,
    )


if __name__ == "__main__":
    main()
