"""
Vibrant Animated Subtitle Generator for ReelerCoaster.
Generates ASS (Advanced SubStation Alpha) subtitle files with word-by-word
karaoke highlight and dynamic pop animations in TikTok/Reels style.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from config import SUBTITLE_STYLES, TARGET_WIDTH, TARGET_HEIGHT


def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def group_words_into_lines(words: List[Dict[str, Any]], max_words_per_line: int = 3, max_gap_sec: float = 1.0) -> List[List[Dict[str, Any]]]:
    """
    Groups individual words into bite-sized phrases (2-4 words)
    optimal for fast vertical mobile reading.
    """
    lines = []
    current_line = []

    for i, w in enumerate(words):
        if not current_line:
            current_line.append(w)
            continue

        gap = w["start"] - current_line[-1]["end"]
        # Break line if too many words, long pause, or punctuation at end of previous word
        prev_word = current_line[-1]["word"]
        has_punctuation = prev_word.endswith((".", "!", "?", "...", ":", ";"))
        
        if len(current_line) >= max_words_per_line or gap > max_gap_sec or has_punctuation:
            lines.append(current_line)
            current_line = [w]
        else:
            current_line.append(w)

    if current_line:
        lines.append(current_line)

    return lines


def generate_ass_subtitles(
    words: List[Dict[str, Any]],
    output_ass_path: str,
    style_name: str = "beast",
    part_label: Optional[str] = None,
    clip_duration: Optional[float] = None
) -> str:
    """
    Builds an ASS subtitle file with karaoke word-level highlighting
    and optional top badge for series parts (e.g. "ЧАСТЬ 1").
    """
    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["beast"])

    # Base ASS template for 1080x1920 portrait
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {TARGET_WIDTH}
PlayResY: {TARGET_HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['fontname']},{style['fontsize'] * 2.5},{style['secondary_color']},&H000000FF,{style['outline_color']},{style['outline_color']},{style['bold']},0,0,0,100,100,2,0,1,{style['outline'] * 2},{style['shadow'] * 2},{style['alignment']},40,40,{style['margin_v'] * 2},1
Style: HeaderBadge,Arial,36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,2,0,1,4.0,2.0,8,40,40,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    # If this is a part in a series, add a sleek top badge
    if part_label:
        badge_end_sec = clip_duration if clip_duration else (words[-1]["end"] + 1.0 if words else 60.0)
        badge_start_str = format_ass_time(0.0)
        badge_end_str = format_ass_time(badge_end_sec)
        # Styled top banner: e.g. "⚡ ЧАСТЬ 1 ⚡" with yellow/cyan highlight
        events.append(
            f"Dialogue: 1,{badge_start_str},{badge_end_str},HeaderBadge,,0,0,0,,{{\\c&H0000FFFF&}}⚡ {part_label} ⚡"
        )

    lines = group_words_into_lines(words, max_words_per_line=3)
    highlight_color = style["primary_color"] # e.g. Yellow
    normal_color = style["secondary_color"]  # e.g. White

    for line_words in lines:
        if not line_words:
            continue
        line_start = line_words[0]["start"]
        line_end = line_words[-1]["end"]

        # For each word in this line, render an event where that word is highlighted
        for active_idx, active_word in enumerate(line_words):
            word_start = active_word["start"]
            # The active state extends until next word starts or line ends
            if active_idx + 1 < len(line_words):
                word_end = line_words[active_idx + 1]["start"]
            else:
                word_end = active_word["end"]

            # If timing overlap or zero length, make it at least 0.15s
            if word_end <= word_start:
                word_end = word_start + 0.15

            start_str = format_ass_time(word_start)
            end_str = format_ass_time(word_end)

            # Build the text with active word pop
            formatted_words = []
            for idx, w in enumerate(line_words):
                clean_w = w["word"].upper()
                if idx == active_idx:
                    # Highlighted active word: Pop scale 115% + primary color
                    formatted_words.append(
                        f"{{\\c{highlight_color}&\\fscx115\\fscy115}}{clean_w}{{\\r}}"
                    )
                else:
                    # Normal word
                    formatted_words.append(
                        f"{{\\c{normal_color}&}}{clean_w}{{\\r}}"
                    )

            dialogue_line = " ".join(formatted_words)
            events.append(
                f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{dialogue_line}"
            )

    full_content = header + "\n".join(events) + "\n"

    out_path = Path(output_ass_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return str(out_path)
