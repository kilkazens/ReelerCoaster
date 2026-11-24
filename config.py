# ReelerCoaster Configuration
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
PROCESSED_DIR = STORAGE_DIR / "processed"
TEMP_DIR = STORAGE_DIR / "temp"

# Ensure directories exist
for d in [STORAGE_DIR, UPLOAD_DIR, PROCESSED_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Ensure PATH is updated from Windows Registry so newly installed winget packages are found
if sys.platform == "win32":
    try:
        import winreg
        user_path = ""
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            try:
                user_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                pass
        if user_path:
            for p in user_path.split(";"):
                if p and p not in os.environ["PATH"]:
                    os.environ["PATH"] = p + ";" + os.environ["PATH"]
    except Exception:
        pass

# Find FFmpeg binary: Check PATH, then winget packages, then imageio_ffmpeg
def get_ffmpeg_path() -> str:
    # 1. Environment variable
    if os.environ.get("FFMPEG_PATH"):
        return os.environ["FFMPEG_PATH"]
    
    # 2. In PATH
    import shutil
    ffmpeg_in_path = shutil.which("ffmpeg")
    if ffmpeg_in_path:
        return ffmpeg_in_path
        
    # 3. Check Winget packages directory dynamically
    winget_pkg_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_pkg_dir.exists():
        for found in winget_pkg_dir.glob("**/ffmpeg.exe"):
            return str(found)

    # 4. Check imageio_ffmpeg default location
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass

    # 5. Standard Windows locations
    candidates = [
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path(os.environ.get("USERPROFILE", "")) / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
            
    return "ffmpeg"

def get_ffprobe_path() -> str:
    import shutil
    probe = shutil.which("ffprobe")
    if probe:
        return probe

    winget_pkg_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_pkg_dir.exists():
        for found in winget_pkg_dir.glob("**/ffprobe.exe"):
            return str(found)

    candidates = [
        Path("C:/Program Files/ffmpeg/bin/ffprobe.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "ffprobe"

FFMPEG_BIN = get_ffmpeg_path()
FFPROBE_BIN = get_ffprobe_path()

# Target Reel dimensions (Vertical 9:16)
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

# Default Highlight Detection settings
DEFAULT_MIN_CLIP_DURATION = 20  # seconds
DEFAULT_MAX_CLIP_DURATION = 65  # seconds
DEFAULT_TARGET_CLIP_COUNT = 3

# Subtitle styling presets
SUBTITLE_STYLES = {
    "beast": {
        "fontname": "Montserrat",
        "fontsize": 22,
        "primary_color": "&H0000FFFF",  # Bright Yellow (BGR format in ASS: 00FFFF is yellow)
        "secondary_color": "&H00FFFFFF", # White
        "outline_color": "&H00000000",  # Black
        "outline": 3.5,
        "shadow": 1.5,
        "bold": 1,
        "alignment": 2, # Bottom Center
        "margin_v": 180, # Above TikTok/Reels caption & button zone
    },
    "neon": {
        "fontname": "Arial",
        "fontsize": 24,
        "primary_color": "&H00FFFF00",  # Cyan
        "secondary_color": "&H00FFFFFF", # White
        "outline_color": "&H00330033",
        "outline": 4.0,
        "shadow": 2.0,
        "bold": 1,
        "alignment": 2,
        "margin_v": 190,
    },
    "minimal": {
        "fontname": "Arial",
        "fontsize": 20,
        "primary_color": "&H00FFFFFF",  # Pure White
        "secondary_color": "&H00AAAAAA",
        "outline_color": "&H00000000",
        "outline": 2.5,
        "shadow": 1.0,
        "bold": 1,
        "alignment": 2,
        "margin_v": 170,
    }
}
