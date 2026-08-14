import subprocess
import os
import re


def get_total_frames(video_path, ffmpeg_path):
    """Uses ffprobe to extract total frame count for progress calculation."""
    ffprobe_path = "ffprobe" if ffmpeg_path == "ffmpeg" else os.path.join(
        os.path.dirname(ffmpeg_path), "ffprobe")

    cmd = [
        ffprobe_path, "-v", "error", "-select_streams", "v:0",
        "-count_packets", "-show_entries", "stream=nb_read_packets",
        "-of", "csv=p=0", video_path
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return int(result.stdout.strip())
    except Exception:
        # Fallback if packet count fails
        return None


def get_video_duration(file_path, ffmpeg_path):
    """Uses ffprobe to etrieve the total duration of a video file in seconds."""
    ffprobe_path = "ffprobe" if ffmpeg_path == "ffmpeg" else os.path.join(
        os.path.dirname(ffmpeg_path), "ffprobe")

    cmd = [
        ffprobe_path, "-v", "error",
        "-show_entries", "format=duration", "-of",
        "default=noprint_wrappers=1:nocey=1",
        file_path,
    ]
    try:
        # Fallback handle if ffprobe names mismatch
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return float(result.stdout.strip())
    except Exception:
        # Fallback parsing via ffmpeg banner if ffprobe is missing
        cmd = [ffmpeg_path, "-i", file_path]
        result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        match = re.search(
            r"Duration:\s*(\d+):(\d+):([0-9.]+)", result.stderr
        )
        if match:
            hours, minutes, seconds = (
                int(match.group(1)),
                int(match.group(2)),
                float(match.group(3)),
            )
            return hours * 3600 + minutes * 60 + seconds
    return None
