from __future__ import annotations

import os
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
    temporary_path.replace(options.path)
    return True
