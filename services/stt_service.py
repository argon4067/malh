from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.config import settings
from models.audio_recording import AudioRecording
from models.transcript import Transcript
from sqlalchemy.orm import Session


MIME_TO_EXT = {
    "audio/webm": "webm",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/ogg": "ogg",
}


def resolve_recording_extension(filename: str | None, content_type: str | None) -> str:
    if content_type and content_type in MIME_TO_EXT:
        return MIME_TO_EXT[content_type]
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    return "webm"


def build_recording_paths(inter_id: int, sel_id: int, ext: str) -> tuple[Path, str]:
    # Rule: storage/audio/interviews/{inter_id}/{sel_id}/answer.{ext}
    relative = f"audio/interviews/{inter_id}/{sel_id}/answer.{ext}"
    absolute = Path(settings.STORAGE_DIR) / relative
    return absolute, relative


def save_recording_and_upsert(
    db: Session,
    inter_id: int,
    sel_id: int,
    filename: str | None,
    content_type: str | None,
    payload: bytes,
    duration_sec: int | None = None,
) -> AudioRecording:
    ext = resolve_recording_extension(filename, content_type)
    absolute_path, relative_path = build_recording_paths(inter_id, sel_id, ext)

    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(payload)

    size_bytes = len(payload)
    stored_path = relative_path.replace("\\", "/")

    record = db.query(AudioRecording).filter(AudioRecording.sel_id == sel_id).first()
    if record is None:
        record = AudioRecording(
            inter_id=inter_id,
            sel_id=sel_id,
            file_path=stored_path,
            mime_type=content_type,
            size_bytes=size_bytes,
            duration_sec=duration_sec if duration_sec is not None else 0,
            upload_status="UPLOADED",
        )
        db.add(record)
    else:
        record.inter_id = inter_id
        record.file_path = stored_path
        record.mime_type = content_type
        record.size_bytes = size_bytes
        if duration_sec is not None:
            record.duration_sec = duration_sec
        record.upload_status = "UPLOADED"

    db.commit()
    db.refresh(record)
    return record


@lru_cache
def _get_openai_client():
    api_key = settings.OPENAI_API_KEY or ""
    if not api_key.strip():
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "openai package is not installed. Add it to requirements."
        ) from exc

    return OpenAI(api_key=api_key)


def transcribe_audio_file(audio_path: Path) -> str:
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    client = _get_openai_client()
    with audio_path.open("rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=audio_file,
            model=settings.OPENAI_STT_MODEL,
            language="ko",
            timeout=settings.OPENAI_STT_TIMEOUT_SEC,
        )

    if isinstance(transcription, str):
        transcript_text = transcription.strip()
    else:
        transcript_text = str(getattr(transcription, "text", "") or "").strip()
    if not transcript_text:
        raise RuntimeError("STT 처리는 완료됐지만 전사 텍스트가 비어 있습니다.")
    return transcript_text


def upsert_transcript(db: Session, sel_id: int, transcript_text: str) -> Transcript:
    transcript = db.query(Transcript).filter(Transcript.sel_id == sel_id).first()
    if transcript is None:
        transcript = Transcript(sel_id=sel_id, transcript_text=transcript_text)
        db.add(transcript)
    else:
        transcript.transcript_text = transcript_text
    db.commit()
    db.refresh(transcript)
    return transcript


from core.exceptions import (
    BadRequestException,
    NotFoundException,
    BaseAPIException,
)

def run_stt_and_update(
    db: Session,
    inter_id: int,
    sel_id: int,
) -> tuple[AudioRecording, Transcript]:
    recording = (
        db.query(AudioRecording)
        .filter(AudioRecording.inter_id == inter_id, AudioRecording.sel_id == sel_id)
        .first()
    )
    if recording is None:
        raise NotFoundException(detail="요청하신 질문의 녹음 파일을 찾을 수 없습니다.")

    audio_abs_path = Path(settings.STORAGE_DIR) / recording.file_path

    if not audio_abs_path.exists():
        recording.upload_status = "FAILED"
        db.commit()
        raise NotFoundException(detail=f"서버에서 오디오 파일을 찾을 수 없습니다. (경로: {recording.file_path})")

    try:
        transcript_text = transcribe_audio_file(audio_abs_path)
        transcript = upsert_transcript(db, sel_id=sel_id, transcript_text=transcript_text)
        recording.upload_status = "STT_DONE"
        db.commit()
        db.refresh(recording)
        return recording, transcript
    except Exception as e:
        recording.upload_status = "FAILED"
        db.commit()
        if isinstance(e, (BadRequestException, NotFoundException)):
            raise
        raise BaseAPIException(detail=f"STT 처리 중 오류가 발생했습니다: {str(e)}") from e
