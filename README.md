# AudioTrimmer

A classic, stylish audio trimmer for desktop.

- Load any audio (m4a, mp3, wav, flac, ogg, opus, aac) via drag & drop or the Open button
- Clear, sharp waveform with smooth zoom (mouse wheel / +/- buttons / Fit)
- Draggable left/right trim handles — click & drag the handle, move the whole selection, or click anywhere to jump
- Play / Pause / Stop transport, space bar shortcut, volume control
- Trim playback: plays only the selected region and stops at its end
- Export the selection to MP3 (128 / 192 / 320 kbps)

## Run

```bash
poetry install
poetry run audiotrimmer
```

Requires Python 3.11+ and `ffmpeg` on PATH (used for loading and MP3 export).