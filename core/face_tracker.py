"""
Face & Head Tracking Module for IRL Mode in ReelerCoaster.
Uses OpenCV YuNet Deep Learning Face Detector (cv2.FaceDetectorYN)
with smoothed trajectory interpolation.
"""

import os
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

YUNET_MODEL_PATH = Path(__file__).resolve().parent.parent / "storage" / "models" / "face_detection_yunet_2023mar.onnx"


class FaceTracker:
    def __init__(self):
        self.detector = None
        self._input_size = (320, 320)
        
        if YUNET_MODEL_PATH.exists():
            try:
                self.detector = cv2.FaceDetectorYN_create(
                    str(YUNET_MODEL_PATH),
                    "",
                    self._input_size,
                    score_threshold=0.6,
                    nms_threshold=0.3,
                    top_k=5
                )
            except Exception as e:
                print(f"[FaceTracker] Warning initializing YuNet: {e}")

    def detect_face_in_frame(self, frame_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        Detects primary face in frame using YuNet.
        Returns (x, y, w, h) in original frame coordinates, or None.
        """
        if self.detector is None or frame_bgr is None:
            return None

        h, w = frame_bgr.shape[:2]
        # Resize to fixed input size for fast neural inference
        infer_w = 320
        infer_h = int(h * (infer_w / w))
        infer_img = cv2.resize(frame_bgr, (infer_w, infer_h))

        self.detector.setInputSize((infer_w, infer_h))
        try:
            _, faces = self.detector.detect(infer_img)
            if faces is None or len(faces) == 0:
                return None

            # Find face with largest bounding box (faces: [x, y, w, h, x1, y1, ...])
            best_face = max(faces, key=lambda f: f[2] * f[3])
            fx, fy, fw, fh = best_face[:4]

            # Scale back up
            scale_x = w / float(infer_w)
            scale_y = h / float(infer_h)

            orig_fx = int(fx * scale_x)
            orig_fy = int(fy * scale_y)
            orig_fw = int(fw * scale_x)
            orig_fh = int(fh * scale_y)

            return (orig_fx, orig_fy, orig_fw, orig_fh)
        except Exception:
            return None

    def compute_smoothed_face_trajectory(
        self,
        video_path: str,
        start_time: float,
        duration: float,
        sample_interval_sec: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Samples video at regular intervals to track face center X and Y,
        interpolating and smoothing to prevent jerky camera motion.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        total_orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080

        cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000.0)
        
        sample_step_frames = max(1, int(fps * sample_interval_sec))
        num_frames = int(duration * fps)

        points = []
        default_center_x = total_orig_w / 2.0
        default_center_y = total_orig_h / 3.0
        last_known_x = default_center_x
        last_known_y = default_center_y

        frame_idx = 0
        while frame_idx < num_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_step_frames == 0:
                face = self.detect_face_in_frame(frame)
                t_sec = start_time + (frame_idx / fps)
                if face is not None:
                    fx, fy, fw, fh = face
                    center_x = fx + fw / 2.0
                    center_y = fy + fh / 2.0
                    last_known_x = center_x
                    last_known_y = center_y
                else:
                    last_known_x = last_known_x * 0.95 + default_center_x * 0.05
                    last_known_y = last_known_y * 0.95 + default_center_y * 0.05

                points.append({
                    "t": t_sec,
                    "x": last_known_x,
                    "y": last_known_y
                })

            frame_idx += 1

        cap.release()

        # Smooth points using rolling exponential moving average
        if points:
            alpha = 0.35
            smoothed_x = points[0]["x"]
            smoothed_y = points[0]["y"]
            for pt in points:
                smoothed_x = alpha * pt["x"] + (1 - alpha) * smoothed_x
                smoothed_y = alpha * pt["y"] + (1 - alpha) * smoothed_y
                pt["x"] = smoothed_x
                pt["y"] = smoothed_y

        return points


def find_average_head_center(video_path: str, start_time: float, duration: float) -> Tuple[int, int]:
    """
    Quickly finds the dominant average face position across the segment.
    Used for rock-solid stationary vertical cropping.
    """
    tracker = FaceTracker()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 960, 540

    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080

    step = max(0.5, duration / 8.0)
    detected_x = []
    detected_y = []

    for i in range(8):
        t = start_time + (i * step)
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ret, frame = cap.read()
        if not ret:
            break
        face = tracker.detect_face_in_frame(frame)
        if face:
            fx, fy, fw, fh = face
            detected_x.append(fx + fw / 2.0)
            detected_y.append(fy + fh / 2.0)

    cap.release()

    if detected_x:
        avg_x = int(np.median(detected_x))
        avg_y = int(np.median(detected_y))
    else:
        avg_x = orig_w // 2
        avg_y = orig_h // 3

    return avg_x, avg_y
