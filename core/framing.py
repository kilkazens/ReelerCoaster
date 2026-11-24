"""
Framing & Layout Engine for ReelerCoaster.
Generates FFmpeg filtergraphs for 9:16 vertical video conversion.
Supports IRL Head-tracking, Gaming Split-Screen (Webcam + Gameplay),
Center Crop, and Blurred Background Fits.
"""

from typing import Dict, Any, Optional
from config import TARGET_WIDTH, TARGET_HEIGHT
from core.face_tracker import find_average_head_center


def build_irl_filtergraph(
    video_path: str,
    orig_w: int,
    orig_h: int,
    start_time: float,
    duration: float,
    subtitle_ass_path: Optional[str] = None
) -> str:
    """
    Builds filtergraph for IRL / Talking Head content.
    Automatically centers on the speaker's face/head, crops to 9:16,
    and scales to 1080x1920.
    """
    # Find head center
    center_x, center_y = find_average_head_center(video_path, start_time, duration)

    # 9:16 target width inside original height
    crop_w = int(orig_h * 9.0 / 16.0)
    crop_h = orig_h

    # Ensure crop dimensions are even
    if crop_w % 2 != 0:
        crop_w -= 1

    # Center crop_x around head center
    crop_x = int(center_x - (crop_w / 2.0))
    # Clamp within frame boundaries
    crop_x = max(0, min(orig_w - crop_w, crop_x))
    crop_y = 0

    filters = [
        f"[0:v]crop={crop_w}:{crop_h}:{crop_x}:{crop_y}[cropped]",
        f"[cropped]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=lanczos[scaled]"
    ]

    last_label = "[scaled]"

    if subtitle_ass_path:
        escaped_sub = subtitle_ass_path.replace("\\", "/").replace(":", "\\:")
        filters.append(f"{last_label}ass='{escaped_sub}'[v]")
    else:
        filters.append(f"{last_label}null[v]")

    return ";".join(filters)


def build_gaming_filtergraph(
    orig_w: int,
    orig_h: int,
    webcam_pos: str = "none",  # none, top_right, top_left, bottom_right, bottom_left, fit_blur
    custom_webcam_box: Optional[Dict[str, float]] = None,
    subtitle_ass_path: Optional[str] = None
) -> str:
    """
    Builds filtergraph for Gaming content.
    - If webcam_pos == 'none': Centered 9:16 crop of action.
    - If webcam_pos == 'fit_blur': Entire 16:9 gameplay centered with blurred top/bottom.
    - If webcam_pos in ['top_right', 'top_left', ...]: Split screen!
        Top ~35% (1080x672) is Webcam, Bottom ~65% (1080x1248) is Gameplay.
    """
    filters = []

    if webcam_pos == "none":
        # Pure center crop
        crop_w = int(orig_h * 9.0 / 16.0)
        if crop_w % 2 != 0:
            crop_w -= 1
        crop_x = max(0, int((orig_w - crop_w) / 2.0))
        
        filters.append(f"[0:v]crop={crop_w}:{orig_h}:{crop_x}:0[c]")
        filters.append(f"[c]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=lanczos[scaled]")
        last_label = "[scaled]"

    elif webcam_pos == "fit_blur":
        # Blurred background + 16:9 gameplay in center
        # Background: scale to fill 1080x1920 + heavy blur
        filters.append(
            f"[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},"
            f"boxblur=25:5[bg]"
        )
        # Foreground: scale to width 1080 keeping aspect ratio
        fg_h = int(TARGET_WIDTH * (orig_h / orig_w))
        if fg_h % 2 != 0:
            fg_h += 1
        filters.append(f"[0:v]scale={TARGET_WIDTH}:{fg_h}:flags=lanczos[fg]")
        # Overlay in center
        overlay_y = (TARGET_HEIGHT - fg_h) // 2
        filters.append(f"[bg][fg]overlay=0:{overlay_y}[comp]")
        last_label = "[comp]"

    else:
        # Split-screen (Webcam + Gameplay)
        # Canvas: 1080 x 1920
        # Webcam height: 680px, Gameplay height: 1240px
        cam_h = 680
        game_h = TARGET_HEIGHT - cam_h # 1240

        # Calculate webcam bounding box in source video
        # Default typical streamer facecam is ~25-30% width, ~25-30% height
        if custom_webcam_box:
            # normalized 0.0 - 1.0
            cx = int(custom_webcam_box.get("x", 0.75) * orig_w)
            cy = int(custom_webcam_box.get("y", 0.0) * orig_h)
            cw = int(custom_webcam_box.get("w", 0.25) * orig_w)
            ch = int(custom_webcam_box.get("h", 0.35) * orig_h)
        else:
            cw = int(orig_w * 0.28)
            ch = int(orig_h * 0.35)
            if webcam_pos == "top_right":
                cx = orig_w - cw
                cy = 0
            elif webcam_pos == "top_left":
                cx = 0
                cy = 0
            elif webcam_pos == "bottom_right":
                cx = orig_w - cw
                cy = orig_h - ch
            elif webcam_pos == "bottom_left":
                cx = 0
                cy = orig_h - ch
            else:
                cx = orig_w - cw
                cy = 0

        # Ensure bounds and even dimensions
        cw = max(20, cw if cw % 2 == 0 else cw - 1)
        ch = max(20, ch if ch % 2 == 0 else ch - 1)
        cx = max(0, min(orig_w - cw, cx))
        cy = max(0, min(orig_h - ch, cy))

        # Split 0:v into two streams
        filters.append("[0:v]split=2[in_cam][in_game]")

        # 1. Webcam crop & scale to 1080x680 (zoom to fill)
        filters.append(
            f"[in_cam]crop={cw}:{ch}:{cx}:{cy},"
            f"scale={TARGET_WIDTH}:{cam_h}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_WIDTH}:{cam_h}[webcam]"
        )

        # 2. Gameplay crop & scale to 1080x1240
        # Center gameplay horizontally
        game_crop_w = int(orig_h * (TARGET_WIDTH / game_h))
        if game_crop_w > orig_w:
            game_crop_w = orig_w
        if game_crop_w % 2 != 0:
            game_crop_w -= 1
        game_crop_x = max(0, (orig_w - game_crop_w) // 2)

        filters.append(
            f"[in_game]crop={game_crop_w}:{orig_h}:{game_crop_x}:0,"
            f"scale={TARGET_WIDTH}:{game_h}:flags=lanczos[gameplay]"
        )

        # 3. Stack webcam on top, gameplay on bottom
        filters.append("[webcam][gameplay]vstack=inputs=2[stacked]")

        # 4. Add subtle neon border separator line between webcam & gameplay
        # Drawbox at y = 678, height 4px
        filters.append(
            "[stacked]drawbox=x=0:y=678:w=1080:h=4:color=0x00E5FF@0.9:t=fill[comp]"
        )
        last_label = "[comp]"

    if subtitle_ass_path:
        escaped_sub = subtitle_ass_path.replace("\\", "/").replace(":", "\\:")
        filters.append(f"{last_label}ass='{escaped_sub}'[v]")
    else:
        filters.append(f"{last_label}null[v]")

    return ";".join(filters)
