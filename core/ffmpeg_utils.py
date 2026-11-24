"""
FFmpeg Utility Functions for ReelerCoaster
Handles probing, cutting, audio extraction, hardware-accelerated encoding,
and complex filtergraph processing.
"""

import os
import json
import re
import subprocess
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from config import FFMPEG_BIN, FFPROBE_BIN


def has_nvenc() -> bool:
    """Check if NVIDIA NVENC hardware encoder is available."""
    try:
        res = subprocess.run(
            [FFMPEG_BIN, "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        return "h264_nvenc" in res.stdout
    except Exception:
        return False


# Cache NVENC capability
USE_NVENC = has_nvenc()


def get_video_info(video_path: str) -> Dict[str, Any]:
    """
    Extract video metadata (width, height, duration, fps, has_audio).
    Uses ffprobe if available, with robust fallback to ffmpeg -i and OpenCV.
    """
    video_path = str(Path(video_path).resolve())
    info: Dict[str, Any] = {
        "width": 1920,
        "height": 1080,
        "duration": 0.0,
        "fps": 30.0,
        "has_audio": False,
        "bitrate": 0
    }

    # Fallback/Primary via ffmpeg -i inspection
    try:
        proc = subprocess.run(
            [FFMPEG_BIN, "-i", video_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10
        )
        output = proc.stderr

        # Duration match: Duration: 00:01:23.45
        dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", output)
        if dur_match:
            h, m, s = dur_match.groups()
            info["duration"] = int(h) * 3600 + int(m) * 60 + float(s)

        # Video stream match: Video: ..., 1920x1080 [SAR ..., 60 fps
        res_match = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", output)
        if res_match:
            info["width"] = int(res_match.group(1))
            info["height"] = int(res_match.group(2))

        fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", output)
        if fps_match:
            info["fps"] = float(fps_match.group(1))

        # Audio stream match
        if "Audio:" in output:
            info["has_audio"] = True

    except Exception as e:
        print(f"[FFmpegUtils] Warning during ffmpeg -i: {e}")

    # Cross-check / supplement with OpenCV if width/height/duration were 0
    if info["duration"] == 0 or info["width"] == 0:
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                if info["width"] == 0:
                    info["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                if info["height"] == 0:
                    info["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                if fps > 0:
                    info["fps"] = float(fps)
                frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                if info["duration"] == 0 and info["fps"] > 0:
                    info["duration"] = frames / info["fps"]
            cap.release()
        except Exception:
            pass

    return info


def extract_audio(video_path: str, output_wav_path: str) -> bool:
    """Extract 16kHz mono WAV audio optimal for Whisper and energy analysis."""
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
        return res.returncode == 0
    except Exception as e:
        print(f"[FFmpegUtils] Audio extraction error: {e}")
        return False


def cut_clip(video_path: str, start_time: float, duration: float, output_path: str) -> bool:
    """Accurately cut a segment from the video."""
    video_codec = "h264_nvenc" if USE_NVENC else "libx264"
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-ss", f"{start_time:.3f}",
        "-i", str(video_path),
        "-t", f"{duration:.3f}",
        "-c:v", video_codec,
        "-preset", "p4" if USE_NVENC else "veryfast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-avoid_negative_ts", "make_zero",
        str(output_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
        return res.returncode == 0
    except Exception as e:
        print(f"[FFmpegUtils] Cut clip error: {e}")
        return False


def run_ffmpeg_filter(input_path: str, filter_complex: str, output_path: str, audio_source: Optional[str] = None) -> bool:
    """Run an FFmpeg command with complex filters and high-performance encoding."""
    video_codec = "h264_nvenc" if USE_NVENC else "libx264"
    preset = "p4" if USE_NVENC else "fast"
    
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", str(input_path),
    ]

    if audio_source and audio_source != input_path:
        cmd.extend(["-i", str(audio_source)])

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", video_codec,
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path)
    ])

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
        if res.returncode != 0:
            print(f"[FFmpegUtils] Filter command failed: {res.stderr}")
            # Try CPU fallback if NVENC failed
            if USE_NVENC and video_codec == "h264_nvenc":
                cmd[cmd.index("h264_nvenc")] = "libx264"
                cmd[cmd.index("p4")] = "veryfast"
                res_cpu = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
                return res_cpu.returncode == 0
        return res.returncode == 0
    except Exception as e:
        print(f"[FFmpegUtils] Filter run error: {e}")
        return False
