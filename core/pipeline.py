"""
End-to-End Processing Pipeline for ReelerCoaster.
Orchestrates downloading, audio extraction, highlight scoring,
smart framing, transcription, and vertical video rendering.
"""

import os
import uuid
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from config import UPLOAD_DIR, PROCESSED_DIR, TEMP_DIR, FFMPEG_BIN
from core.downloader import (
    download_from_url,
    save_uploaded_file,
    get_media_info,
    download_audio_only,
    download_video_section
)
from core.ffmpeg_utils import get_video_info, extract_audio, cut_clip, run_ffmpeg_filter
from core.highlight_detector import detect_highlights, smart_split_full_video
from core.transcriber import transcribe_clip_audio
from core.subtitle_burner import generate_ass_subtitles
from core.framing import build_irl_filtergraph, build_gaming_filtergraph


class ReelerPipeline:
    def __init__(self, job_id: Optional[str] = None):
        self.job_id = job_id or str(uuid.uuid4())[:8]
        self.job_dir = PROCESSED_DIR / self.job_id
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = TEMP_DIR / self.job_id
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def process(
        self,
        source_type: str, # "url" or "file"
        source_val: Any,  # url string or local path
        mode: str = "irl", # "irl" or "gaming"
        webcam_pos: str = "none",
        custom_webcam_box: Optional[Dict[str, float]] = None,
        split_strategy: str = "highlights", # "highlights" or "full_split"
        target_part_duration: float = 60.0,
        enable_subtitles: bool = True,
        subtitle_style: str = "beast",
        target_clips: int = 3,
        min_clip_duration: float = 25.0,
        max_clip_duration: float = 60.0,
        whisper_model: str = "base",
        language: Optional[str] = None,
        cleanup_source: bool = True,
        progress_cb: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes the entire pipeline and returns output clips metadata.
        """
        def update_progress(pct: int, msg: str):
            if progress_cb:
                progress_cb(pct, msg)
            print(f"[Pipeline {self.job_id}] [{pct}%] {msg}")

        update_progress(5, "Инициализация и получение видео...")

        # 1. Acquire video & audio analysis stream
        full_wav_path = self.temp_dir / "full_audio.wav"

        if source_type == "url":
            update_progress(10, "Получение информации о видео...")
            meta = get_media_info(source_val)
            title = meta.get("title", "Online Video")
            duration = meta.get("duration", 0.0)
            orig_w = meta.get("width", 1920)
            orig_h = meta.get("height", 1080)
            vinfo = {"width": orig_w, "height": orig_h, "duration": duration, "has_audio": True}
            input_video_path = None # Full video is never downloaded!

            if duration <= 0:
                raise ValueError("Не удалось определить длительность видео по ссылке.")

            # Audio-First Architecture: Download ONLY audio track (saves 98% of disk and bandwidth)
            update_progress(20, f"Загрузка аудиодорожки для AI-анализа (экономия 98% диска)...")
            if not download_audio_only(source_val, str(full_wav_path)):
                # Fallback to full download if audio-only stream fails
                print("[Pipeline] Audio-only fallback to full download...")
                media_info = download_from_url(source_val)
                input_video_path = media_info["path"]
                extract_audio(input_video_path, str(full_wav_path))
        else:
            input_video_path = str(source_val)
            title = Path(input_video_path).stem
            update_progress(20, "Анализ характеристик локального видео...")
            vinfo = get_video_info(input_video_path)
            orig_w = vinfo["width"]
            orig_h = vinfo["height"]
            duration = vinfo["duration"]

            if duration <= 0:
                raise ValueError("Не удалось определить длительность видео или видео повреждено.")

            update_progress(30, "Извлечение аудиодорожки для анализа...")
            if not extract_audio(input_video_path, str(full_wav_path)):
                raise RuntimeError("Ошибка при извлечении аудио из файла.")

        # 2. Detect Highlights or Smart Split Whole Video
        if split_strategy == "full_split":
            update_progress(40, f"Умный анализ видео и деление на серии (по ~{int(target_part_duration)} сек)...")
            min_p = max(25.0, target_part_duration * 0.70)
            max_p = target_part_duration * 1.35
            highlights = smart_split_full_video(
                str(full_wav_path),
                total_duration=duration,
                target_part_duration=target_part_duration,
                min_part_duration=min_p,
                max_part_duration=max_p
            )
            update_progress(50, f"Видео поделено на {len(highlights)} частей. Начало нарезки...")
        else:
            update_progress(40, "Умный анализ энергии и поиск лучших моментов...")
            highlights = detect_highlights(
                str(full_wav_path),
                target_count=target_clips,
                min_clip_duration=min_clip_duration,
                max_clip_duration=max_clip_duration
            )
            update_progress(50, f"Найдено моментов: {len(highlights)}. Начало нарезки и оформления...")

        output_clips: List[Dict[str, Any]] = []

        total_hl = len(highlights)
        for idx, hl in enumerate(highlights):
            clip_idx = idx + 1
            clip_start = hl["start"]
            clip_dur = hl["duration"]
            base_pct = 50 + int((idx / total_hl) * 45)

            update_progress(base_pct, f"Обработка клипа #{clip_idx}/{total_hl}: {hl['title']}...")

            # Acquire ONLY this specific segment
            raw_clip_path = self.temp_dir / f"raw_clip_{clip_idx}.mp4"
            if source_type == "url" and input_video_path is None:
                update_progress(base_pct + 1, f"Клип #{clip_idx}: точечная загрузка {clip_dur:.0f} сек (без скачивания всего видео)...")
                download_video_section(source_val, clip_start, clip_start + clip_dur, str(raw_clip_path))
            else:
                cut_clip(input_video_path, clip_start, clip_dur, str(raw_clip_path))

            # Extract audio of the clip for Whisper
            clip_wav_path = self.temp_dir / f"clip_{clip_idx}.wav"
            extract_audio(str(raw_clip_path), str(clip_wav_path))

            # Transcribe & generate subtitles if enabled
            ass_sub_path = None
            if enable_subtitles and vinfo["has_audio"]:
                try:
                    update_progress(base_pct + 2, f"Клип #{clip_idx}: генерация динамических субтитров (Whisper)...")
                    words = transcribe_clip_audio(
                        str(clip_wav_path),
                        language=language,
                        model_size=whisper_model
                    )
                    part_label = f"ЧАСТЬ {hl['part_number']}" if "part_number" in hl else None
                    if words:
                        ass_file = self.temp_dir / f"sub_{clip_idx}.ass"
                        ass_sub_path = generate_ass_subtitles(
                            words,
                            str(ass_file),
                            style_name=subtitle_style,
                            part_label=part_label,
                            clip_duration=clip_dur
                        )
                except Exception as e:
                    print(f"[Pipeline] Ошибка генерации субтитров для клипа #{clip_idx}: {e}")

            # Smart Framing & Layout
            update_progress(base_pct + 5, f"Клип #{clip_idx}: кадрирование 9:16 ({mode.upper()}) и рендеринг...")

            if mode == "irl":
                filter_graph = build_irl_filtergraph(
                    str(raw_clip_path),
                    orig_w,
                    orig_h,
                    start_time=0.0,
                    duration=clip_dur,
                    subtitle_ass_path=ass_sub_path
                )
            else:
                filter_graph = build_gaming_filtergraph(
                    orig_w,
                    orig_h,
                    webcam_pos=webcam_pos,
                    custom_webcam_box=custom_webcam_box,
                    subtitle_ass_path=ass_sub_path
                )

            final_clip_filename = f"reel_{clip_idx}.mp4"
            final_clip_path = self.job_dir / final_clip_filename

            # Render
            success = run_ffmpeg_filter(
                str(raw_clip_path),
                filter_graph,
                str(final_clip_path)
            )

            if not success or not final_clip_path.exists():
                print(f"[Pipeline] Fallback simple cut for clip #{clip_idx}")
                if raw_clip_path.exists():
                    shutil.copyfile(str(raw_clip_path), str(final_clip_path))
                elif input_video_path:
                    cut_clip(input_video_path, clip_start, clip_dur, str(final_clip_path))

            # Generate preview thumbnail
            thumb_filename = f"thumb_{clip_idx}.jpg"
            thumb_path = self.job_dir / thumb_filename
            import subprocess
            subprocess.run([
                FFMPEG_BIN, "-y",
                "-ss", "00:00:01",
                "-i", str(final_clip_path),
                "-vframes", "1",
                "-vf", "scale=360:640",
                str(thumb_path)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Instantly remove raw chunk and audio clip to free disk
            try:
                raw_clip_path.unlink(missing_ok=True)
                clip_wav_path.unlink(missing_ok=True)
            except Exception:
                pass

            output_clips.append({
                "clip_index": clip_idx,
                "title": hl["title"],
                "start": clip_start,
                "end": hl["end"],
                "duration": round(clip_dur, 1),
                "filename": final_clip_filename,
                "video_url": f"/storage/processed/{self.job_id}/{final_clip_filename}",
                "thumbnail_url": f"/storage/processed/{self.job_id}/{thumb_filename}" if thumb_path.exists() else None
            })

        # --- Automatic Disk Cleanup ---
        update_progress(98, "Очистка временных файлов и исходника для экономии диска...")
        
        # 1. Clean temporary files (audio cuts, ass subtitles, raw chunks)
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"[Pipeline] Ошибка очистки temp: {e}")

        # 2. Clean raw source video if stored in uploads
        if cleanup_source:
            try:
                src_path = Path(input_video_path).resolve()
                upload_root = UPLOAD_DIR.resolve()
                if src_path.exists() and (upload_root in src_path.parents or src_path.parent == upload_root):
                    src_path.unlink(missing_ok=True)
                    print(f"[Pipeline] Исходник '{src_path.name}' успешно удален для экономии места на диске.")
            except Exception as e:
                print(f"[Pipeline] Ошибка при удалении исходника: {e}")

        update_progress(100, f"Готово! Создано рилсов: {len(output_clips)} (исходники очищены).")

        return {
            "job_id": self.job_id,
            "title": title,
            "total_duration": duration,
            "clips": output_clips
        }
