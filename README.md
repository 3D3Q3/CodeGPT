# CodeGPT Library Scanner

`library_scanner.py` is a CLI tool for discovering document-like files within a
root directory while prioritizing safety and deduplication.

## Features
- Dry-run by default: previews planned outputs (summary + detailed listings)
  and requires explicit confirmation before any filesystem writes.
- Recursive discovery that skips zero-byte files, hidden/temporary items, names
  containing "part", and non-target media types (audio/video).
- Normalizes and deduplicates matches using case-insensitive paths plus a
  name/size fingerprint.
- Produces both a concise categorized listing and a detailed list with absolute
  paths for downstream tooling.
- Supports exporting results to JSON or structured text files.
- Provides an interactive organization stage to rename/remove categories and
  move entries before any copying occurs (list-only changes; no filesystem writes).
- Offers a staged per-category copy workflow that prompts before every action,
  performs dry-run previews, and writes a log to help undo or inspect copies.

## Usage
```bash
python library_scanner.py /path/to/root \
  --include-ext .pdf .epub \
  --output-json scan.json \
  --output-text scan.txt
```

### Options
- `root`: root directory to scan.
- `--include-ext`: space-delimited extensions to include; overrides the default
  target set (`.pdf`, `.epub`, `.docx`, `.doc`, `.txt`, `.mobi`, `.azw`, `.azw3`,
  `.rtf`, `.md`).
- `--exclude-ext`: extensions to exclude (case-insensitive).
- `--output-json`: path to write JSON results (requires `--apply`).
- `--output-text`: path to write structured text results (requires `--apply`).
- `--apply`: enable filesystem writes; otherwise a dry-run preview is shown.
- `--yes`: skip confirmation prompts when used with `--apply`.
- `--allow-media`: include audio/video files instead of skipping them.
- `--copy-dest`: optional destination directory for staged category copies;
  the script also prompts for this before scanning.
- `--copy-log`: path to the copy log (defaults to `<copy-dest>/copy_log.txt`).

### Organization and staged copy workflow
1. When the program starts it asks for a copy destination before scanning. If
   provided (or supplied via `--copy-dest`), it prepares a per-category plan
   without touching the source tree.
2. After scanning and previewing results, the CLI offers an organization stage.
   You can rename categories, delete categories, move individual entries to
   different categories, or remove entries entirely. Every change asks for
   confirmation and only affects the in-memory list (no files are touched).
   Finishing this step “locks in” the list that will be used for copying.
3. The CLI then offers to begin the staged copy. For each category it first
   performs a dry-run preview that lists every planned copy into a category-
   named folder inside the destination.
4. Only after the user confirms does it copy the files (not folders), skipping
   zero-byte files and leaving any existing destination files untouched.
5. A log file records each action so you can audit or undo changes if needed.

### Safety behavior
- Dry-run previews by default and refuses to write outputs unless `--apply` is
  provided.
- Even with `--apply`, the CLI prompts for confirmation unless `--yes` is
  supplied for automation.
- Filters avoid destructive operations and ignore zero-byte, hidden, temporary,
  and media files unless explicitly allowed.
- Copy operations only target the destination directory you choose; the source
  library is never modified.

## Local test dataset
Run `python tools/create_test_dataset.py` to generate a repeatable fixture under
`test_data/` with:
- Sample categories (Mathematics, Physics, Computer Programming, Machine
  Learning, Cookbooks, etc.).
- One file for each targeted extension plus hidden/temp/partial/media/zero-byte
  examples and duplicates to exercise filters.
- A clean `test_data/library_destination` directory you can use as a copy
  target during staged copy tests.

Re-running the script resets both the source and destination test directories to
their initial state so you can safely rerun scanner experiments.
