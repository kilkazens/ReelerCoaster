"""
Video Downloader & Ingestion Module for ReelerCoaster.
Implements the 'Audio-First + Range-Section' streaming architecture:
1. Fetches metadata without downloading.
2. Downloads ONLY audio (~30-60MB) for highlight/speech analysis.
3. Downloads ONLY the specific 30-60s video sections needed for the reels.
The multi-gigabyte full video is NEVER stored on disk!
"""

import os
import re
import uuid
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List
from config import UPLOAD_DIR, FFMPEG_BIN

NODE_BIN = shutil.which("node")


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe file naming."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = clean.replace(" ", "_")
    return clean[:60] if clean else "video"


def find_aria2c() -> Optional[str]:
    """Find aria2c executable in PATH or standard winget locations."""
    in_path = shutil.which("aria2c")
    if in_path:
        return in_path
    
    winget_pkg_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_pkg_dir.exists():
        for found in winget_pkg_dir.glob("**/aria2c.exe"):
            return str(found)

    links_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "aria2c.exe"
    if links_dir.exists():
        return str(links_dir)

    return None


def get_media_info(url: str) -> Dict[str, Any]:
    """
    Extracts video metadata without downloading any media.
    """
    import yt_dlp

    ydl_opts: Dict[str, Any] = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        }
    }
    if NODE_BIN:
        ydl_opts['js_runtimes'] = {'node': {}}

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        meta = ydl.extract_info(url, download=False)
        media_id = meta.get("id") or hashlib.md5(url.encode()).hexdigest()[:10]
        extractor = meta.get("extractor", "video").lower().replace(":", "_")
        
        # Dimensions
        w = meta.get("width") or 1920
        h = meta.get("height") or 1080
        if not w or not h:
            for f in meta.get("formats", []):
                if f.get("width") and f.get("height"):
                    w = max(w, f["width"])
                    h = max(h, f["height"])

        return {
            "id": media_id,
            "extractor": extractor,
            "title": meta.get("title", "Online Video"),
            "duration": float(meta.get("duration") or 0.0),
            "width": int(w),
            "height": int(h),
            "uploader": meta.get("uploader", ""),
            "thumbnail": meta.get("thumbnail"),
            "url": url
        }


def download_audio_only(
    url: str,
    output_wav_path: str,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None
) -> bool:
    """
    Downloads ONLY the audio track from the URL directly into a 16kHz mono WAV file.
    Fast (5-15s), minimal size (30-60MB even for hours of stream).
    """
    import yt_dlp

    out_stem = str(Path(output_wav_path).with_suffix(""))
    ydl_opts: Dict[str, Any] = {
        'format': 'ba/b',
        'outtmpl': out_stem + '.%(ext)s',
        'ffmpeg_location': FFMPEG_BIN,
        'quiet': True,
        'no_warnings': True,
        'retries': 10,
        'fragment_retries': 10,
        'socket_timeout': 30,
        'concurrent_fragment_downloads': 10,
        'http_chunk_size': 10485760,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
        }],
        'postprocessor_args': [
            '-ar', '16000',
            '-ac', '1'
        ]
    }
    if NODE_BIN:
        ydl_opts['js_runtimes'] = {'node': {}}
    if progress_hook:
        ydl_opts['progress_hooks'] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        actual_wav = Path(out_stem + '.wav')
        target_wav = Path(output_wav_path)
        if actual_wav.exists() and actual_wav != target_wav:
            if target_wav.exists():
                target_wav.unlink(missing_ok=True)
            actual_wav.rename(target_wav)

        return target_wav.exists() and target_wav.stat().st_size > 1000
    except Exception as e:
        print(f"[Downloader] Audio-only download error: {e}")
        return False


def download_video_section(
    url: str,
    start_sec: float,
    end_sec: float,
    output_mp4_path: str,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None
) -> bool:
    """
    Downloads ONLY the specified time range [start_sec, end_sec] from the URL.
    Does NOT download the rest of the video.
    """
    import yt_dlp
    import yt_dlp.utils

    out_stem = str(Path(output_mp4_path).with_suffix(""))
    ydl_opts: Dict[str, Any] = {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
        'outtmpl': out_stem + '.%(ext)s',
        'merge_output_format': 'mp4',
        'ffmpeg_location': FFMPEG_BIN,
        'quiet': True,
        'no_warnings': True,
        'retries': 10,
        'fragment_retries': 10,
        'socket_timeout': 30,
        'concurrent_fragment_downloads': 10,
        'http_chunk_size': 10485760,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'download_ranges': yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)]),
        'force_keyframes_at_cuts': True
    }
    if NODE_BIN:
        ydl_opts['js_runtimes'] = {'node': {}}
    if progress_hook:
        ydl_opts['progress_hooks'] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        actual_mp4 = Path(out_stem + '.mp4')
        target_mp4 = Path(output_mp4_path)
        if actual_mp4.exists() and actual_mp4 != target_mp4:
            if target_mp4.exists():
                target_mp4.unlink(missing_ok=True)
            actual_mp4.rename(target_mp4)

        return target_mp4.exists() and target_mp4.stat().st_size > 1000
    except Exception as e:
        print(f"[Downloader] Video section download error: {e}")
        return False


def download_from_url(
    url: str,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Dict[str, Any]:
    """
    Full video downloader with deduplication (used when full download is explicitly needed).
    """
    import yt_dlp

    aria2_path = find_aria2c()
    meta = get_media_info(url)
    media_id = meta["id"]
    extractor = meta["extractor"]
    title = meta["title"]
    clean_title = sanitize_filename(title)
    base_file_prefix = f"{extractor}_{media_id}"

    # Check deduplication
    for existing in UPLOAD_DIR.glob(f"{base_file_prefix}*"):
        if existing.is_file() and existing.stat().st_size > 1024 * 1024:
            print(f"[Downloader] Видео '{title}' уже скачано ранее: {existing.name}")
            return {
                "id": media_id,
                "title": title,
                "duration": meta["duration"],
                "path": str(existing.resolve()),
                "source": "url",
                "url": url,
                "cached": True
            }

    output_template = str(UPLOAD_DIR / f"{base_file_prefix}_{clean_title}.%(ext)s")
    ydl_opts: Dict[str, Any] = {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'ffmpeg_location': FFMPEG_BIN,
        'quiet': True,
        'no_warnings': True,
        'concurrent_fragment_downloads': 10,
        'http_chunk_size': 10485760,
        'buffersize': 1024 * 1024 * 16,
        'retries': 10,
        'fragment_retries': 10,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        }
    }
    if NODE_BIN:
        ydl_opts['js_runtimes'] = {'node': {}}
    if aria2_path:
        ydl_opts['external_downloader'] = aria2_path
        ydl_opts['external_downloader_args'] = ['-x', '16', '-s', '16', '-k', '1M', '--min-split-size=1M']

    if progress_hook:
        ydl_opts['progress_hooks'] = [progress_hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        matched = list(UPLOAD_DIR.glob(f"{base_file_prefix}*.mp4"))
        final_filename = str(matched[0].resolve()) if matched else output_template

        return {
            "id": media_id,
            "title": title,
            "duration": meta["duration"],
            "uploader": meta.get("uploader", ""),
            "path": final_filename,
            "source": "url",
            "url": url,
            "cached": False
        }


def save_uploaded_file(file_bytes_or_stream, original_filename: str) -> Dict[str, Any]:
    """Save an uploaded local file to uploads directory."""
    clean_name = sanitize_filename(Path(original_filename).stem)
    ext = Path(original_filename).suffix.lower() or ".mp4"
    file_id = str(uuid.uuid4())[:8]
    target_path = UPLOAD_DIR / f"upload_{file_id}_{clean_name}{ext}"

    if hasattr(file_bytes_or_stream, "read"):
        with open(target_path, "wb") as f:
            shutil.copyfileobj(file_bytes_or_stream, f)
    elif isinstance(file_bytes_or_stream, bytes):
        with open(target_path, "wb") as f:
            f.write(file_bytes_or_stream)
    else:
        shutil.copyfile(str(file_bytes_or_stream), str(target_path))

    return {
        "id": file_id,
        "title": clean_name,
        "path": str(target_path.resolve()),
        "source": "upload",
        "original_filename": original_filename
    }
