#!/usr/bin/env python3
"""
TikTok subtitle extractor.
Usage:
    python3 extract_tiktok_subtitles.py <tiktok_url>

Dependencies:
    pip install yt-dlp requests
"""

import sys
import os
import json
import re
import subprocess
import tempfile
import shutil

try:
    import requests
except ImportError:
    requests = None


def extract_with_ytdlp(url: str) -> str | None:
    """Try to extract subtitles using yt-dlp."""
    if not shutil.which("yt-dlp"):
        print("[yt-dlp] not found, trying pip install...")
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp", "-q"], check=False)

    tmpdir = tempfile.mkdtemp()
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs", "zh-Hans,zh-Hant,zh,en",
                "--sub-format", "vtt/srt/best",
                "--skip-download",
                "--no-warnings",
                "-o", os.path.join(tmpdir, "%(id)s"),
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Also try JSON dump for subtitle URLs
        info_result = subprocess.run(
            [
                "yt-dlp",
                "--dump-json",
                "--skip-download",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        subtitle_text = []

        # Parse subtitle files downloaded to tmpdir
        for fname in os.listdir(tmpdir):
            fpath = os.path.join(tmpdir, fname)
            if fname.endswith(".vtt") or fname.endswith(".srt"):
                with open(fpath, encoding="utf-8") as f:
                    raw = f.read()
                subtitle_text.append(parse_subtitle_file(raw, fname))

        if subtitle_text:
            return "\n\n".join(subtitle_text)

        # Fall back to parsing subtitle URLs from JSON info
        if info_result.returncode == 0 and info_result.stdout.strip():
            try:
                info = json.loads(info_result.stdout.strip().splitlines()[-1])
                return extract_subs_from_info(info)
            except (json.JSONDecodeError, IndexError):
                pass

        if result.returncode != 0:
            print(f"[yt-dlp error] {result.stderr[:500]}")
        return None

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def extract_subs_from_info(info: dict) -> str | None:
    """Download and parse subtitle files listed in yt-dlp JSON info."""
    if not requests:
        return None

    subs = info.get("subtitles", {})
    auto_subs = info.get("automatic_captions", {})

    # Prefer manual subs; fall back to auto
    for lang_dict, label in [(subs, "subtitles"), (auto_subs, "auto-captions")]:
        for lang in ("zh-Hans", "zh-Hant", "zh", "en", *lang_dict.keys()):
            entries = lang_dict.get(lang, [])
            for entry in entries:
                fmt = entry.get("ext", "")
                sub_url = entry.get("url", "")
                if not sub_url:
                    continue
                try:
                    resp = requests.get(sub_url, timeout=30)
                    resp.raise_for_status()
                    return f"[{label} / {lang}]\n" + parse_subtitle_file(resp.text, f"file.{fmt}")
                except Exception as exc:
                    print(f"  Could not fetch {lang} {label}: {exc}")
    return None


def parse_subtitle_file(raw: str, filename: str) -> str:
    """Strip timing lines from VTT/SRT and return plain text."""
    lines = raw.splitlines()
    out = []

    if filename.endswith(".vtt"):
        # Skip WebVTT header block
        in_header = True
        for line in lines:
            if in_header:
                if line.strip() == "" and out:
                    in_header = False
                elif re.match(r"^\d{2}:\d{2}", line) or "-->" in line:
                    in_header = False
                else:
                    continue
            # Skip timing lines, cue identifiers, and empty lines
            if "-->" in line:
                continue
            if re.match(r"^\d+$", line.strip()):
                continue
            if line.strip().startswith("WEBVTT"):
                continue
            text = re.sub(r"<[^>]+>", "", line)  # strip inline tags
            if text.strip():
                out.append(text.strip())
    elif filename.endswith(".srt"):
        for line in lines:
            if re.match(r"^\d+$", line.strip()):
                continue
            if "-->" in line:
                continue
            text = re.sub(r"<[^>]+>", "", line)
            if text.strip():
                out.append(text.strip())
    else:
        out = [l for l in lines if l.strip()]

    # Deduplicate consecutive identical lines (common in auto-captions)
    deduped = []
    prev = None
    for line in out:
        if line != prev:
            deduped.append(line)
            prev = line

    return "\n".join(deduped)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <tiktok_url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Extracting subtitles from: {url}\n")

    text = extract_with_ytdlp(url)

    if text:
        print("=" * 60)
        print("SUBTITLES")
        print("=" * 60)
        print(text)
    else:
        print("No subtitles found for this video.")
        print("\nTips:")
        print("  - Make sure yt-dlp is up-to-date: yt-dlp -U")
        print("  - Some videos don't have subtitles enabled.")
        print("  - TikTok may require cookies for some regions.")
        print("  - Try: yt-dlp --cookies-from-browser chrome <url>")


if __name__ == "__main__":
    main()
