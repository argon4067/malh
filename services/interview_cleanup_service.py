from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from core.config import settings
from models.audio_recording import AudioRecording
from models.interview_session import InterviewSession
from services.storage_cleanup_service import prune_empty_audio_tree, remove_session_audio_tree

logger = logging.getLogger(__name__)


def purge_interview_audio_files(db: Session, inter_id: int) -> dict[str, int]:
    rows = db.query(AudioRecording.file_path).filter(AudioRecording.inter_id == inter_id).all()
    removed_files = sum(1 for row in rows if (row.file_path or "").strip())
    remove_session_audio_tree(Path(settings.STORAGE_DIR), inter_id)

    removed_audio = (
        db.query(AudioRecording)
        .filter(AudioRecording.inter_id == inter_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    prune_empty_audio_tree(Path(settings.STORAGE_DIR))
    return {
        "removed_audio": int(removed_audio),
        "removed_files": int(removed_files),
    }


def cleanup_stale_in_progress_session_audio(
    db: Session,
    stale_before: datetime,
) -> dict[str, int]:
    rows = (
        db.query(
            AudioRecording.inter_id.label("inter_id"),
            func.max(AudioRecording.updated_at).label("last_audio_at"),
        )
        .join(InterviewSession, InterviewSession.inter_id == AudioRecording.inter_id)
        .filter(InterviewSession.inter_status == "IN_PROGRESS")
        .group_by(AudioRecording.inter_id)
        .all()
    )

    stale_session_ids = [
        int(row.inter_id)
        for row in rows
        if row.last_audio_at and row.last_audio_at <= stale_before
    ]
    summary = {
        "stale_sessions": 0,
        "removed_audio": 0,
        "removed_files": 0,
    }

    for inter_id in stale_session_ids:
        try:
            result = purge_interview_audio_files(db=db, inter_id=inter_id)
        except Exception:
            db.rollback()
            logger.exception("STALE_AUDIO_CLEANUP_FAILED inter_id=%s", inter_id)
            continue

        summary["stale_sessions"] += 1
        summary["removed_audio"] += int(result["removed_audio"])
        summary["removed_files"] += int(result["removed_files"])

    return summary
