"""Audio loading, peak computation and MP3 export (pydub + ffmpeg)."""

from __future__ import annotations

import array
import math
import os
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment

SUPPORTED_EXT = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".wma", ".aiff", ".aif"}


@dataclass
class AudioFile:
    path: str
    segment: AudioSegment
    duration_ms: int
    frame_rate: int
    channels: int

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)


def open_audio(path: str | Path) -> AudioFile:
    seg = AudioSegment.from_file(str(path))
    if seg.channels > 2:
        seg = seg.set_channels(2)
    return AudioFile(
        path=str(path),
        segment=seg,
        duration_ms=len(seg),
        frame_rate=seg.frame_rate,
        channels=seg.channels,
    )


_TYPECODES = {1: "b", 2: "h", 4: "i"}


def _samples(seg: AudioSegment) -> array.array:
    tc = _TYPECODES.get(seg.sample_width)
    if tc is None:
        raise ValueError(f"unsupported sample width: {seg.sample_width}")
    return array.array(tc, seg.raw_data)


def compute_peaks(seg: AudioSegment, start_ms: int, end_ms: int, buckets: int) -> list[tuple[float, float]]:
    """Return `buckets` (lo, hi) pairs normalized to -1..1 (relative to file peak).

    Only the [start_ms, end_ms) region is analysed, which makes zoomed views cheap.
    """
    if buckets < 1 or end_ms <= start_ms:
        return [(0.0, 0.0)] * max(buckets, 1)

    samples = _samples(seg)
    total = len(samples)
    if total == 0:
        return [(0.0, 0.0)] * buckets

    scale = seg.frame_rate / 1000.0
    start_i = max(0, int(start_ms * scale * seg.channels))
    end_i = min(total, int(end_ms * scale * seg.channels))
    if end_i <= start_i:
        return [(0.0, 0.0)] * buckets

    peak_abs = max((abs(s) for s in samples), default=1) or 1

    win = end_i - start_i
    step = max(1, math.ceil(win / buckets))
    out: list[tuple[float, float]] = []
    chunks = math.ceil(win / step)
    for i in range(chunks):
        lo = start_i + i * step
        hi = min(end_i, lo + step)
        window = samples[lo:hi]
        if len(window):
            mn = min(window)
            mx = max(window)
        else:
            mn = mx = 0
        out.append((mn / peak_abs, mx / peak_abs))
    if len(out) < buckets:
        out.extend([(0.0, 0.0)] * (buckets - len(out)))
    return out[:buckets]


def export_mp3(seg: AudioSegment, start_ms: int, end_ms: int, out_path: str | Path, bitrate: str = "192k") -> None:
    clip = seg[max(0, start_ms):max(start_ms, end_ms)]
    clip.export(str(out_path), format="mp3", bitrate=bitrate)


def default_out_name(src_path: str) -> str:
    p = Path(src_path)
    return str(p.with_name(f"{p.stem}_trimmed.mp3"))