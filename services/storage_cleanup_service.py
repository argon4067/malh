from __future__ import annotations

import shutil
from pathlib import Path


def _is_within_root(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def prune_empty_dirs_upward(storage_dir: Path, relative_file_path: str, stop_rel: str = "audio/interviews") -> int:
    """
    Remove empty parent directories of a deleted file path up to stop_rel (exclusive).
    """
    if not (relative_file_path or "").strip():
        return 0

    root = storage_dir.resolve()
    stop_dir = (storage_dir / stop_rel).resolve()
    target_file = (storage_dir / relative_file_path).resolve()
    current = target_file.parent
    removed = 0

    while _is_within_root(root, current) and current != stop_dir and current != current.parent:
        try:
            current.rmdir()  # succeeds only if empty
            removed += 1
            current = current.parent
        except OSError:
            break
        except Exception:
            break

    return removed


def prune_empty_audio_tree(storage_dir: Path, base_rel: str = "audio/interviews") -> int:
    """
    Best-effort pruning for empty directories under storage/audio/interviews.
    """
    base_dir = (storage_dir / base_rel).resolve()
    root = storage_dir.resolve()
    removed = 0

    if not base_dir.exists() or not base_dir.is_dir():
        return 0
    if not _is_within_root(root, base_dir):
        return 0

    # Bottom-up walk: remove leaf empty dirs first.
    for dirpath, dirnames, filenames in __import__("os").walk(str(base_dir), topdown=False):
        current = Path(dirpath)
        if current == base_dir:
            continue
        if dirnames or filenames:
            continue
        try:
            current.rmdir()
            removed += 1
        except Exception:
            continue

    return removed


def remove_session_audio_tree(
    storage_dir: Path,
    inter_id: int,
    base_rel: str = "audio/interviews",
) -> bool:
    """
    Remove a single interview session tree under storage/audio/interviews/{inter_id}
    and then best-effort prune now-empty parent directories up to the storage root.
    """
    base_dir = (storage_dir / base_rel / str(inter_id)).resolve()
    root = storage_dir.resolve()

    if not _is_within_root(root, base_dir):
        return False
    if not base_dir.exists():
        return False

    try:
        shutil.rmtree(base_dir)
    except FileNotFoundError:
        return False

    current = base_dir.parent
    while current == root or _is_within_root(root, current):
        try:
            current.rmdir()
        except OSError:
            break
        except Exception:
            break

        if current == root:
            break
        current = current.parent

    return True
