"""
Highlight & Moment Detector for ReelerCoaster.
Analyzes audio energy, loudness variance, and speech pacing
to find the most engaging, viral segments.
"""

import math
import wave
import struct
from typing import List, Dict, Any, Tuple
import numpy as np


def compute_audio_energy_profile(wav_path: str, chunk_duration_sec: float = 0.5) -> Tuple[np.ndarray, float]:
    """
    Reads a 16kHz mono WAV file and computes the RMS energy for each time chunk.
    Returns (energy_array, total_duration).
    """
    with wave.open(str(wav_path), 'rb') as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        
        total_duration = n_frames / float(framerate)
        if total_duration <= 0:
            return np.array([]), 0.0

        # Read frames as 16-bit integers
        raw_bytes = wf.readframes(n_frames)
        
        if sampwidth == 2:
            dtype = np.int16
        elif sampwidth == 4:
            dtype = np.int32
        else:
            dtype = np.uint8

        audio_samples = np.frombuffer(raw_bytes, dtype=dtype)
        if n_channels > 1:
            audio_samples = audio_samples[::n_channels]

        # Normalize to -1.0 .. 1.0
        max_val = float(np.iinfo(dtype).max) if dtype != np.uint8 else 255.0
        audio_samples = audio_samples.astype(np.float32) / max_val

        chunk_size = int(framerate * chunk_duration_sec)
        num_chunks = int(len(audio_samples) / chunk_size)

        if num_chunks == 0:
            return np.array([np.sqrt(np.mean(audio_samples ** 2))]), total_duration

        reshaped = audio_samples[:num_chunks * chunk_size].reshape((num_chunks, chunk_size))
        # Root-mean-square (RMS) energy
        energy = np.sqrt(np.mean(reshaped ** 2, axis=1))

        # Smooth slightly using a moving average
        kernel_size = 3
        if len(energy) >= kernel_size:
            smoothed = np.convolve(energy, np.ones(kernel_size) / kernel_size, mode='same')
        else:
            smoothed = energy

        return smoothed, total_duration


def detect_highlights(
    wav_path: str,
    target_count: int = 3,
    min_clip_duration: float = 20.0,
    max_clip_duration: float = 75.0,
    chunk_sec: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Intelligent Dynamic Event-Arc Highlight Detector.
    Instead of fixed time windows, it locates peak emotional/action anchors
    (shouting, laughter, gameplay hype) and organically tracks where the moment
    began (setup/hook pause) and where it concluded (energy decay & speech pause).
    Each highlight has an organic, variable duration.
    """
    energy, total_duration = compute_audio_energy_profile(wav_path, chunk_duration_sec=chunk_sec)
    
    if len(energy) == 0 or total_duration <= min_clip_duration:
        return [{
            "index": 1,
            "start": 0.0,
            "end": max(1.0, total_duration),
            "duration": round(total_duration, 1),
            "score": 100.0,
            "title": f"Хайлайт (00:00 - {int(total_duration//60):02d}:{int(total_duration%60):02d})"
        }]

    mean_energy = float(np.mean(energy))
    std_energy = float(np.std(energy))
    valley_threshold = max(0.001, mean_energy * 0.75)
    spike_threshold = mean_energy + (std_energy * 0.5)

    num_chunks = len(energy)
    min_chunks = max(1, int(min_clip_duration / chunk_sec))
    max_chunks = int(max_clip_duration / chunk_sec)

    # 1. Detect Peak Anchors (Local maxima significantly above baseline)
    peak_indices = []
    window_radius = int(2.5 / chunk_sec) # 2.5s local neighborhood

    for i in range(window_radius, num_chunks - window_radius):
        val = energy[i]
        if val > spike_threshold:
            # Check if it's the maximum in its local neighborhood
            if val == np.max(energy[i - window_radius : i + window_radius + 1]):
                peak_indices.append((i, val))

    # Sort peaks descending by loudness
    peak_indices.sort(key=lambda x: x[1], reverse=True)

    # 2. For each peak, grow the clip organically:
    # Look back for setup/hook valley, look forward for resolution valley
    candidates = []

    for peak_idx, peak_val in peak_indices:
        t_peak = peak_idx * chunk_sec

        # --- Search backward for event start ---
        # Look back between 4s and 18s before peak for a quiet pause
        max_lookback_chunks = min(peak_idx, int(18.0 / chunk_sec))
        min_lookback_chunks = min(peak_idx, int(4.0 / chunk_sec))

        best_start_idx = max(0, peak_idx - int(6.0 / chunk_sec))
        lowest_start_energy = float("inf")

        for back_i in range(peak_idx - min_lookback_chunks, peak_idx - max_lookback_chunks - 1, -1):
            if back_i < 0:
                break
            e_val = energy[back_i]
            if e_val < lowest_start_energy:
                lowest_start_energy = e_val
                best_start_idx = back_i
            # If we found a distinct pause
            if e_val <= valley_threshold:
                best_start_idx = back_i
                break

        # --- Search forward for event resolution ---
        # Look forward after peak until energy settles down and hits a pause
        min_lookahead_chunks = int(12.0 / chunk_sec)
        max_lookahead_chunks = int(50.0 / chunk_sec)

        best_end_idx = min(num_chunks - 1, peak_idx + int(15.0 / chunk_sec))
        lowest_end_energy = float("inf")

        search_end_limit = min(num_chunks, peak_idx + max_lookahead_chunks)
        for fwd_i in range(peak_idx + min_lookahead_chunks, search_end_limit):
            e_val = energy[fwd_i]
            if e_val < lowest_end_energy:
                lowest_end_energy = e_val
                best_end_idx = fwd_i
            # If excitement ended and hit a quiet speech pause
            if e_val <= valley_threshold and (fwd_i - best_start_idx) >= min_chunks:
                best_end_idx = fwd_i
                break

        # --- Adjust boundaries to satisfy duration limits ---
        dur_chunks = best_end_idx - best_start_idx

        # If too short, expand forward or backward
        if dur_chunks < min_chunks:
            needed = min_chunks - dur_chunks
            add_back = min(best_start_idx, needed // 2)
            add_fwd = min(num_chunks - 1 - best_end_idx, needed - add_back)
            best_start_idx -= add_back
            best_end_idx += add_fwd

        # If too long, trim from the quieter tail
        if (best_end_idx - best_start_idx) > max_chunks:
            best_end_idx = best_start_idx + max_chunks

        start_t = round(best_start_idx * chunk_sec, 2)
        end_t = round(min(total_duration, best_end_idx * chunk_sec), 2)
        clip_dur = round(end_t - start_t, 2)

        if clip_dur < min_clip_duration * 0.8:
            continue

        # Score the moment: peak intensity + average excitement + contrast ratio
        clip_window = energy[best_start_idx : best_end_idx + 1]
        avg_clip_energy = float(np.mean(clip_window)) if len(clip_window) > 0 else 0.0
        contrast = peak_val / (mean_energy + 1e-4)

        score = (peak_val * 45.0) + (avg_clip_energy * 35.0) + (min(contrast, 5.0) * 20.0)

        candidates.append({
            "start": start_t,
            "end": end_t,
            "duration": clip_dur,
            "score": score,
            "peak_time": t_peak
        })

    # Sort descending by score
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # 3. Non-Maximum Suppression (Filter out overlapping highlights)
    selected: List[Dict[str, Any]] = []

    for cand in candidates:
        if len(selected) >= target_count:
            break
        # Check temporal overlap
        overlaps = False
        for s in selected:
            overlap_start = max(cand["start"], s["start"])
            overlap_end = min(cand["end"], s["end"])
            overlap_duration = max(0.0, overlap_end - overlap_start)
            
            # If overlapping by more than 8 seconds or 30% of either clip
            if overlap_duration > 8.0 or (overlap_duration / min(cand["duration"], s["duration"]) > 0.3):
                overlaps = True
                break

        if not overlaps:
            selected.append(cand)

    # Fallback if no peaks detected (very quiet or uniform video)
    if not selected:
        clip_dur = min(max_clip_duration, max(min_clip_duration, total_duration / max(1, target_count)))
        for i in range(min(target_count, int(total_duration // clip_dur) or 1)):
            st = i * clip_dur
            en = min(total_duration, st + clip_dur)
            selected.append({
                "start": round(st, 2),
                "end": round(en, 2),
                "duration": round(en - st, 2),
                "score": 50.0
            })

    # Sort chronologically and label
    selected.sort(key=lambda x: x["start"])
    for idx, c in enumerate(selected):
        c["index"] = idx + 1
        m_st, s_st = int(c["start"] // 60), int(c["start"] % 60)
        m_en, s_en = int(c["end"] // 60), int(c["end"] % 60)
        c["title"] = f"Хайлайт #{idx + 1} ({m_st:02d}:{s_st:02d} - {m_en:02d}:{s_en:02d})"

    return selected


def smart_split_full_video(
    wav_path: str,
    total_duration: float,
    target_part_duration: float = 60.0,
    min_part_duration: float = 40.0,
    max_part_duration: float = 90.0,
    chunk_sec: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Splits the entire video into consecutive parts (Часть 1, Часть 2, ...)
    with intelligent boundary detection.
    Finds the most favorable cut points (silence gaps, sentence endings,
    or speech pauses) near target_part_duration so words are never cut abruptly.
    """
    energy, wav_dur = compute_audio_energy_profile(wav_path, chunk_duration_sec=chunk_sec)
    dur = max(total_duration, wav_dur)

    # If video is already shorter than max single part duration
    if dur <= max_part_duration * 1.1:
        return [{
            "index": 1,
            "part_number": 1,
            "start": 0.0,
            "end": dur,
            "duration": dur,
            "title": f"Часть 1 (00:00 - {int(dur//60):02d}:{int(dur%60):02d})",
            "score": 100.0
        }]

    mean_energy = float(np.mean(energy)) if len(energy) > 0 else 0.01

    parts: List[Dict[str, Any]] = []
    curr_t = 0.0

    while curr_t < dur:
        remaining = dur - curr_t

        # If remaining time is close enough to one part, don't leave an awkward stub
        if remaining <= max_part_duration * 1.15:
            parts.append({
                "index": len(parts) + 1,
                "part_number": len(parts) + 1,
                "start": curr_t,
                "end": dur,
                "duration": dur - curr_t,
                "title": f"Часть {len(parts) + 1} ({int(curr_t//60):02d}:{int(curr_t%60):02d} - {int(dur//60):02d}:{int(dur%60):02d})",
                "score": 90.0
            })
            break

        # Search window for optimal split point
        search_start = curr_t + min_part_duration
        search_end = min(dur - 20.0, curr_t + max_part_duration)

        if search_start >= search_end or len(energy) == 0:
            best_split = curr_t + target_part_duration
        else:
            best_split = curr_t + target_part_duration
            best_loss = float("inf")

            step_sec = 0.5
            candidate_t = search_start
            while candidate_t <= search_end:
                c_idx = int(candidate_t / chunk_sec)
                # Compute local pause energy (average over ~1 second around candidate)
                idx_start = max(0, c_idx - 1)
                idx_end = min(len(energy), c_idx + 2)
                pause_energy = float(np.mean(energy[idx_start:idx_end])) if idx_end > idx_start else mean_energy

                # Normalized distance from ideal target duration
                dist_from_target = abs((candidate_t - curr_t) - target_part_duration)
                norm_dist = dist_from_target / target_part_duration

                # Loss = silence priority (70%) + closeness to target duration (30%)
                loss = (pause_energy / (mean_energy + 1e-5)) * 0.70 + (norm_dist ** 1.3) * 0.30

                if loss < best_loss:
                    best_loss = loss
                    best_split = candidate_t

                candidate_t += step_sec

        # Round to neat 2 decimal places
        best_split = round(best_split, 2)
        part_dur = round(best_split - curr_t, 2)

        parts.append({
            "index": len(parts) + 1,
            "part_number": len(parts) + 1,
            "start": curr_t,
            "end": best_split,
            "duration": part_dur,
            "title": f"Часть {len(parts) + 1} ({int(curr_t//60):02d}:{int(curr_t%60):02d} - {int(best_split//60):02d}:{int(best_split%60):02d})",
            "score": 95.0
        })

        curr_t = best_split

    return parts

