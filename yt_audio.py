"""Download audio-only from a YouTube URL.

Requirements:
    pip install yt-dlp
    ffmpeg installed on PATH (brew install ffmpeg)

Usage:
    python yt_audio.py <youtube_url> [output_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

from yt_dlp import YoutubeDL


def download_audio(url: str, output_dir: str | Path = ".") -> Path:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": False,
        "noplaylist": True,
    }

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        final_path = Path(ydl.prepare_filename(info)).with_suffix(".mp3")

    return final_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python yt_audio.py <youtube_url> [output_dir]")
        sys.exit(1)

    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    path = download_audio(url, out)
    print(f"\nSaved: {path}")
