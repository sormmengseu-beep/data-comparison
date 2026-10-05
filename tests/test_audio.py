import math
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication, QFileDialog

from app.dialogs import ExportOptions
from app.exporter import export_preview
from app.main_window import MainWindow
from app.widgets.preview_widget import PreviewWidget


def write_wav(path: Path, duration: float = 0.4) -> None:
    sample_rate = 8_000
    frames = bytearray()
    for index in range(round(sample_rate * duration)):
        sample = round(8_000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.audio_path = Path(self.directory.name) / "soundtrack.wav"
        write_wav(self.audio_path)
        self.window = MainWindow()

    def tearDown(self):
        self.window.pause_playback()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_import_creates_player_updates_timeline_and_prevents_duplicates(self):
        player = MagicMock()
        output = MagicMock()
        player.mediaStatusChanged = MagicMock()
        with patch("app.main_window.QMediaPlayer", return_value=player), patch(
            "app.main_window.QAudioOutput", return_value=output
        ), patch.object(
            QFileDialog,
            "getOpenFileName",
            return_value=(str(self.audio_path), ""),
        ):
            self.window.import_audio()
            self.window.import_audio()

        resolved = str(self.audio_path.resolve())
        self.assertEqual(self.window.project.audio_paths, [resolved])
        self.assertEqual(self.window._audio_source_paths, (resolved,))
        self.assertEqual(len(self.window._audio_players), 1)
        self.assertIs(self.window.timeline.canvas.project, self.window.project)
        player.setSource.assert_called_once()
        output.setMuted.assert_called_once_with(False)
        output.setVolume.assert_called_once_with(1.0)

        self.window.toggle_playback()
        player.play.assert_called_once()
        player.setPosition.reset_mock()
        self.window.set_current_time(1.25)
        player.setPosition.assert_called_once_with(1250)
        self.window.pause_playback()
        player.pause.assert_called()

    def test_unused_realtek_alternate_output_falls_back_to_speakers(self):
        alternate = MagicMock()
        alternate.id.return_value = QByteArray(b"alternate")
        alternate.description.return_value = "Realtek HD Audio 2nd output (Realtek(R) Audio)"
        alternate.isNull.return_value = False
        speakers = MagicMock()
        speakers.id.return_value = QByteArray(b"speakers")
        speakers.description.return_value = "Speakers (Realtek(R) Audio)"
        self.window._audio_device_key = ""

        with patch(
            "app.main_window.QMediaDevices.defaultAudioOutput",
            return_value=alternate,
        ):
            selected = self.window._choose_audio_device_id([alternate, speakers])

        self.assertEqual(selected, bytes(b"speakers").hex())

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for audio muxing")
    def test_video_export_contains_imported_audio_stream(self):
        preview = PreviewWidget()
        output = Path(self.directory.name) / "with_audio.mp4"
        options = ExportOptions(output, "mp4", 160, 90, 10, 0.4)
        self.assertTrue(
            export_preview(
                preview,
                options,
                0,
                audio_paths=[str(self.audio_path)],
            )
        )
        probe = subprocess.run(
            [
                shutil.which("ffprobe") or "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        preview.deleteLater()
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.strip(), "audio")


if __name__ == "__main__":
    unittest.main()
