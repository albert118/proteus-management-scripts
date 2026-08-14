import subprocess
import os
import sys


def check_dependencies(ffmpeg_path):
    """Verify that ffmpeg is available in the system path."""
    ffprobe_path = "ffprobe" if ffmpeg_path == "ffmpeg" else os.path.join(
        os.path.dirname(ffmpeg_path), "ffprobe")
    try:
        subprocess.run([ffmpeg_path, "-version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([ffprobe_path, "-version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print(
            f"Error: Executable binaries missing. Verify paths for: '{ffmpeg_path}' and '{ffprobe_path}'")
        sys.exit(1)


def check_inputs(original, reencoded):
    if not os.path.exists(original):
        print(
            f"Error: The original input video file does not exist: {original}")
        sys.exit(1)

    if not os.path.exists(reencoded):
        print(
            f"Error: The re-encoded input video file does not exist: {reencoded}")
        sys.exit(1)
