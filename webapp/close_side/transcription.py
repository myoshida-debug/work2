from __future__ import annotations

import contextlib
import mimetypes
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path

from django.conf import settings


DEFAULT_WHISPER_MODEL_NAME = 'small'
DEFAULT_WHISPER_DEVICE = 'cpu'
DEFAULT_WHISPER_COMPUTE_TYPE = 'int8'
DEFAULT_WHISPER_LANGUAGE = 'ja'
DEFAULT_WHISPER_LOCAL_FILES_ONLY = False
MAX_TRANSCRIPTION_AUDIO_BYTES = 25 * 1024 * 1024
WHISPER_MODEL_FILENAMES = (
    'config.json',
    'model.bin',
    'tokenizer.json',
    'vocabulary.txt',
)


class TranscriptionError(RuntimeError):
    pass


class TranscriptionConfigurationError(TranscriptionError):
    pass


class TranscriptionRequestError(TranscriptionError):
    pass


class TranscriptionServiceError(TranscriptionError):
    pass


def _configured_value(name: str, default: str = '') -> str:
    value = getattr(settings, name, None)
    if value is None or value == '':
        value = os.environ.get(name, default)
    return str(value or default).strip()


def _configured_bool(name: str, default: bool) -> bool:
    raw_value = _configured_value(name, 'true' if default else 'false').lower()
    return raw_value in {'1', 'true', 'yes', 'on'}


def _configured_int(name: str, default: int) -> int:
    raw_value = _configured_value(name, str(default))
    try:
        return int(raw_value)
    except ValueError:
        return default


def _whisper_model_name() -> str:
    return _configured_value('CLOSE_SIDE_WHISPER_MODEL_NAME', DEFAULT_WHISPER_MODEL_NAME)


def _whisper_download_root() -> str:
    return _configured_value('CLOSE_SIDE_WHISPER_DOWNLOAD_ROOT') or _configured_value('CLOSE_SIDE_WHISPER_MODEL_PATH')


def _is_complete_whisper_model_dir(candidate: Path) -> bool:
    return candidate.is_dir() and all((candidate / filename).exists() for filename in WHISPER_MODEL_FILENAMES)


def _find_complete_whisper_model_dir(root: Path) -> Path | None:
    if _is_complete_whisper_model_dir(root):
        return root
    if not root.exists():
        return None

    candidates = [
        candidate
        for candidate in root.iterdir()
        if candidate.is_dir() and _is_complete_whisper_model_dir(candidate)
    ]
    candidates.extend(
        candidate
        for candidate in root.glob('**/snapshots/*')
        if _is_complete_whisper_model_dir(candidate)
    )
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate.stat().st_mtime)


def _whisper_local_model_path() -> Path | None:
    model_path = _configured_value('CLOSE_SIDE_WHISPER_MODEL_PATH')
    if not model_path:
        return None

    candidate = Path(model_path)
    return _find_complete_whisper_model_dir(candidate)


def _resolve_whisper_model_source() -> tuple[str, str | None]:
    local_model_path = _whisper_local_model_path()
    if local_model_path is not None:
        return str(local_model_path), None
    return _whisper_model_name(), _whisper_download_root() or None


def _whisper_device() -> str:
    return _configured_value('CLOSE_SIDE_WHISPER_DEVICE', DEFAULT_WHISPER_DEVICE)


def _whisper_compute_type() -> str:
    return _configured_value('CLOSE_SIDE_WHISPER_COMPUTE_TYPE', DEFAULT_WHISPER_COMPUTE_TYPE)


def _whisper_local_files_only() -> bool:
    return _configured_bool('CLOSE_SIDE_WHISPER_LOCAL_FILES_ONLY', DEFAULT_WHISPER_LOCAL_FILES_ONLY)


def _whisper_language() -> str:
    return _configured_value('CLOSE_SIDE_WHISPER_LANGUAGE', DEFAULT_WHISPER_LANGUAGE)


def _whisper_beam_size() -> int:
    return max(1, _configured_int('CLOSE_SIDE_WHISPER_BEAM_SIZE', 5))


def _build_transcription_prompt(template_type: str) -> str:
    prompt_parts = ['以下は医療・看護系の日本語音声です。']
    template_type = str(template_type or '').strip()
    if template_type:
        prompt_parts.append(f'文書種別は「{template_type}」です。')
    prompt_parts.append('固有名詞や医療用語をできるだけ正確に日本語で文字起こししてください。')
    return ''.join(prompt_parts)


def _read_audio_payload(audio_file) -> tuple[bytes, str, str, int]:
    if audio_file is None:
        raise TranscriptionRequestError('音声ファイルがありません。')

    audio_name = os.path.basename(str(getattr(audio_file, 'name', '') or 'audio.webm'))
    audio_name = re.sub(r'[\r\n"]+', '_', audio_name)
    content_type = str(
        getattr(audio_file, 'content_type', '')
        or mimetypes.guess_type(audio_name)[0]
        or 'application/octet-stream'
    )

    if hasattr(audio_file, 'read'):
        content = audio_file.read()
        if hasattr(audio_file, 'seek'):
            with contextlib.suppress(Exception):
                audio_file.seek(0)
    else:
        content = bytes(audio_file)

    if content is None:
        content = b''
    if not isinstance(content, (bytes, bytearray)):
        content = bytes(content)

    audio_bytes = bytes(content)
    audio_size = len(audio_bytes)
    return audio_bytes, audio_name, content_type, audio_size


def _write_temp_audio_file(audio_bytes: bytes, audio_name: str) -> Path:
    suffix = Path(audio_name).suffix or '.audio'
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp_file.write(audio_bytes)
        temp_file.flush()
    finally:
        temp_file.close()
    return Path(temp_file.name)


def _normalize_transcript_text(text: str) -> str:
    normalized = str(text or '').replace('\u3000', ' ')
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


def _import_whisper_model_class():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent
        raise TranscriptionConfigurationError(
            'ローカル Whisper を使うには faster-whisper が必要です。'
        ) from exc
    return WhisperModel


@lru_cache(maxsize=8)
def _load_whisper_model(
    model_identifier: str,
    device: str,
    compute_type: str,
    local_files_only: bool,
    download_root: str | None = None,
):
    whisper_model_class = _import_whisper_model_class()
    try:
        kwargs = {
            'device': device,
            'compute_type': compute_type,
            'local_files_only': local_files_only,
        }
        if download_root:
            kwargs['download_root'] = download_root
        return whisper_model_class(model_identifier, **kwargs)
    except Exception as exc:
        raise TranscriptionConfigurationError(
            'ローカル Whisper モデルを読み込めませんでした。'
            ' CLOSE_SIDE_WHISPER_MODEL_PATH がモデル本体(model.binを含む)か、'
            ' もしくはダウンロード先のルートディレクトリかを確認してください。'
            ' 必要なら CLOSE_SIDE_WHISPER_DOWNLOAD_ROOT も指定できます。'
            f' 元のエラー: {exc}'
        ) from exc


def _transcribe_audio_file(audio_path: Path, template_type: str) -> tuple[str, str]:
    model_identifier, download_root = _resolve_whisper_model_source()
    model = _load_whisper_model(
        model_identifier,
        _whisper_device(),
        _whisper_compute_type(),
        _whisper_local_files_only(),
        download_root=download_root,
    )
    initial_prompt = _build_transcription_prompt(template_type)

    try:
        segments, info = model.transcribe(
            str(audio_path),
            language=_whisper_language(),
            task='transcribe',
            initial_prompt=initial_prompt,
            beam_size=_whisper_beam_size(),
            vad_filter=True,
        )
    except Exception as exc:
        raise TranscriptionServiceError(f'文字起こしに失敗しました: {exc}') from exc

    transcript_text = _normalize_transcript_text(''.join(segment.text or '' for segment in segments))
    if not transcript_text:
        raise TranscriptionServiceError('文字起こし結果が空でした。')

    detected_language = str(getattr(info, 'language', '') or '').strip()
    return transcript_text, detected_language


def transcribe_audio_file(audio_file, *, template_type: str = '') -> dict[str, str]:
    audio_bytes, audio_name, _content_type, audio_size = _read_audio_payload(audio_file)
    if audio_size <= 0:
        raise TranscriptionRequestError('音声ファイルが空です。')
    if audio_size > MAX_TRANSCRIPTION_AUDIO_BYTES:
        raise TranscriptionRequestError('音声ファイルは 25MB 以下にしてください。')

    audio_path = _write_temp_audio_file(audio_bytes, audio_name)
    try:
        transcript_text, detected_language = _transcribe_audio_file(audio_path, template_type=template_type)
    finally:
        with contextlib.suppress(FileNotFoundError, OSError):
            audio_path.unlink()

    result = {
        'text': transcript_text,
        'model': _whisper_model_name(),
    }
    if detected_language:
        result['language'] = detected_language
    return result
