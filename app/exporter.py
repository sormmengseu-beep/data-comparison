from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

from app.dialogs import ExportOptions
from app.widgets.preview_widget import PreviewWidget


class ExportError(Exception):
    """Raised when preview output cannot be rendered or written."""


ProgressCallback = Callable[[int, int], bool]


def export_preview(
    preview: PreviewWidget,
    options: ExportOptions,
    current_time: float,
    progress: ProgressCallback | None = None,
    audio_paths: list[str] | None = None,
) -> bool:
    options.path.parent.mkdir(parents=True, exist_ok=True)
    size = QSize(options.width, options.height)
    if options.format_name == "png":
        image = preview.render_frame(current_time, size)
        if not image.save(str(options.path), "PNG"):
            raise ExportError("The PNG file could not be written.")
        return True

    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise ExportError("Video export requires OpenCV and NumPy.") from exc

    valid_audio_paths = [
        Path(path).resolve()
        for path in (audio_paths or [])
        if Path(path).is_file()
    ]
    ffmpeg = shutil.which("ffmpeg") if valid_audio_paths else None
    if valid_audio_paths and ffmpeg is None:
        raise ExportError(
            "Audio export requires FFmpeg. Install FFmpeg or remove the audio tracks."
        )

    suffix = f".{options.format_name}"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".comparison_export_", suffix=suffix, dir=options.path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)

    codec = "mp4v" if options.format_name == "mp4" else "XVID"
    writer = cv2.VideoWriter(
        str(temporary_path),
        cv2.VideoWriter_fourcc(*codec),
        float(options.fps),
        (options.width, options.height),
    )
    if not writer.isOpened():
        temporary_path.unlink(missing_ok=True)
        raise ExportError(f"The {options.format_name.upper()} encoder could not be opened.")

    total_frames = max(1, round(options.duration * options.fps))
    completed = False
    try:
        for frame_index in range(total_frames):
            if progress is not None and not progress(frame_index, total_frames):
                return False
            seconds = min(options.duration, frame_index / options.fps)
            image = preview.render_frame(seconds, size)
            rgb = image.convertToFormat(QImage.Format.Format_RGB888)
            buffer = rgb.bits()
            array = np.frombuffer(buffer, dtype=np.uint8).reshape(rgb.height(), rgb.bytesPerLine())
            frame = array[:, : rgb.width() * 3].reshape(rgb.height(), rgb.width(), 3)
            writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        completed = True
    finally:
        writer.release()
        if not completed:
            temporary_path.unlink(missing_ok=True)

    if progress is not None:
        progress(total_frames, total_frames)
    if valid_audio_paths:
        try:
            _mux_audio(
                ffmpeg or "ffmpeg",
                temporary_path,
                options.path,
                valid_audio_paths,
                options.duration,
                options.format_name,
            )
        finally:
            temporary_path.unlink(missing_ok=True)
    else:
        temporary_path.replace(options.path)
    return True


def _mux_audio(
    ffmpeg: str,
    video_path: Path,
    output_path: Path,
    audio_paths: list[Path],
    duration: float,
    format_name: str,
) -> None:
    """Copy rendered video and mix all imported audio tracks into the result."""
    descriptor, muxed_name = tempfile.mkstemp(
        prefix=".comparison_audio_",
        suffix=f".{format_name}",
        dir=output_path.parent,
    )
    os.close(descriptor)
    muxed_path = Path(muxed_name)
    muxed_path.unlink(missing_ok=True)
    command = [ffmpeg, "-y", "-v", "error", "-i", str(video_path)]
    for audio_path in audio_paths:
        command.extend(["-i", str(audio_path)])
    if len(audio_paths) == 1:
        audio_map = "1:a:0"
    else:
        inputs = "".join(f"[{index}:a:0]" for index in range(1, len(audio_paths) + 1))
        command.extend(
            [
                "-filter_complex",
                f"{inputs}amix=inputs={len(audio_paths)}:duration=longest:dropout_transition=2[aout]",
            ]
        )
        audio_map = "[aout]"
    audio_codec = "aac" if format_name == "mp4" else "libmp3lame"
    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            audio_map,
            "-c:v",
            "copy",
            "-c:a",
            audio_codec,
            "-t",
            f"{max(0.1, duration):.6f}",
            str(muxed_path),
        ]
    )
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            startupinfo=startupinfo,
        )
        if result.returncode != 0 or not muxed_path.is_file():
            detail = result.stderr.strip().splitlines()
            reason = detail[-1] if detail else "FFmpeg did not create the output file."
            raise ExportError(f"The audio track could not be added to the video: {reason}")
        muxed_path.replace(output_path)
    finally:
        muxed_path.unlink(missing_ok=True)
