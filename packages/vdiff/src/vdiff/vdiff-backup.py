#!/usr/bin/env python3

"""
Check given video stream for issues using a few strategies. This works for lossy re-encodes
by checking the result against a snapshot of the original file. 

This calculates the following stats:
- Netflix's VMAF (https://en.wikipedia.org/wiki/Video_Multimethod_Assessment_Fusion)
- PSNR (peak signal to noise ratio)
- Structural Similarity Index Measure (SSIM)
The (VMAF) score of is betwen [0, 100]
- 93 - 95 is imperceptible to the human eye
- 100 is perfect (unlikely).

The PSNR is decible scale
higher is better
- relies on MSE
- a standard, 8-bit, image with a "good" score would be ~[30, 50] db

SSIM compares some other common visuals,
- luminance, contrast, and structure
- not captured by other stats
- [0.0, 1.0] range. 1.0 is identical to original, and 0.0 is no similarity

This script uses ffmpeg to calculate the various stats that factor into the VMAF score. This in turn relise on having the libvmaf filter compiled with it.
This is not standard typically! However, there are other precompiled binaries that can be used.

```sh
wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz
tar -xf ffmpeg-git-amd64-static.tar.xz
cd ffmpeg-*-amd64-static/
# test if the filter is available
./ffmpeg -filters | grep vmaf
```
"""

import subprocess
import json
import os
import sys
import multiprocessing
import argparse
import math
import re

# Safely import or instruct on installing tqdm
# FIX: Make tqdm completely optional so it runs inside bare Docker containers
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    print('TQDM not found - optionally install it to enable fancy progress tracking')
    HAS_TQDM = False


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


def parse_arguments():
    # Calculate default thread balance (Total threads minus 2, clamping at a minimum of 1)
    default_threads = 16  # recommended for HEVC
    # max(1, multiprocessing.cpu_count() - 2)

    parser = argparse.ArgumentParser(
        description="High-performance video similarity comparison tool using VMAF and PSNR. Optimized for multi-threaded CPUs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Positional required arguments
    parser.add_argument(
        "original", help="Path to the reference (source) video file.")
    parser.add_argument(
        "reencoded", help="Path to the lossy re-encoded video file to evaluate.")

    # Optional parametrized flags
    parser.add_argument(
        "-f", "--ffmpeg-path",
        default="ffmpeg",
        help="Path to the custom FFmpeg static binary executable file."
    )
    parser.add_argument(
        "-o", "--output-log",
        default="results.json",
        help="Temporary JSON log file path used by FFmpeg to dump raw calculations."
    )
    parser.add_argument(
        "-t", "--threads",
        type=int,
        default=default_threads,
        help="Maximum thread ceiling allocated to the processing calculation engine."
    )
    parser.add_argument(
        "--parse-results",
        action="store_true",
        help="Do not process - simply parse the given result file from --output-log."
    )

    # score QA gates
    parser.add_argument(
        "--min-vmaf",
        type=float,
        default=93.0,
        help="The minimum acceptable VMAF score required to pass verification."
    )
    parser.add_argument(
        "--min-psnr",
        type=float,
        default=35.0,
        help="The minimum acceptable Peak Signal-to-Noise Ratio (PSNR) in dB."
    )
    parser.add_argument(
        "--min-ssim",
        type=float,
        default=0.95,
        help="The minimum acceptable Structural Similarity Index (SSIM) score (0.0 to 1.0)."
    )

    return parser.parse_args()


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


def analyze_video_similarity(original, reencoded, ffmpeg_path, output_log, thread_limit):
    """
    Computes VMAF, PSNR, and SSIM between the original and lossy re-encoded video.
    Filters sync the videos by scaling the re-encoded file to match the original dimensions.
    """

    total_frames = get_total_frames(original, ffmpeg_path)
    if not total_frames:
        print("Warning: Could not determine total frame count. Progress bar will track raw frame count instead of a percentage.")

    print(f"Analyzing: \n  Original: {original}\n  Re-encoded: {reencoded}\n")
    print("Running quality metrics via FFmpeg (this may take a few minutes)...")

    # FFmpeg filtergraph: Scales re-encoded to match original, then computes VMAF, PSNR, SSIM
    # Outputs a JSON log containing frame-by-frame and summary data
    # FIX: Modern syntax uses model='version=vmaf_v0.6.1' or model='path=...'
    #   1. Pipes and colons are isolated cleanly to avoid 'Invalid argument' syntax parsing bugs
    # FIX: FILTER GRAPH FOR MODERN FFMPEG (7.1+):
    #   1. Swaps deprecated scale2ref out for modern scale filter with reference hooks (rw:rh)
    #   2. Removes feature=name=ssim to prevent library initialization failure.
    # HW_ACCEL: NVIDIA CUDA interactions
    #    1. Downloads CUDA GPU frames to RAM
    #    2. converts format, and matches scale
    # FIX: dont use HW_ACCEL for this work!
    #    1. actually better to leave this on the CPU
    #    2. threadripper tuned filter, decodes natively on your 32 threads
    #    3. passes standard memory spaces seamlessly directly into the libvmaf array
    #    4. requires zero memory and driver overhead (no prop' driver needed), as static binaries vs. host kernel space are a bitch
    #    5. thread balancing on big CPU is easy anyway. Avoids copying to-from GPU memspace
    #    6. configure thread consumption to optimise usage
    # FIX: the libvmaf filter defaults to a single thread unless it is explicitly told to multithread
    #    1. Forces libvmaf filter to split calculation over thread_limit threads and sample every 2nd frame
    # FIX:
    #    - stats are resolved as frame-by-frame outputs to log files or stdio
    #    - a log output can be massive (megabytes) and doesn't include the final computation anyway
    #    1. read the computed final stats from stdout and avoid writing to a log file entirely
    # FIX:
    #    - PSNR and SSIM filters desire matching container timebases
    #    - apply settb=1/90000,setpts=N to the filter graph to align the x2 sources
    #    - this adds significant overhead though. if the encoding pipeline preserved the original container's timebase this could be avoided entirel
    filter_complex = (
        "[0:v]settb=1/90000,setpts=N[clean_ref]; "
        "[1:v]settb=1/90000,setpts=N[clean_dist]; "
        "[clean_ref]split=3[ref_vmaf][ref_ssim][ref_psnr]; "
        "[clean_dist]split=3[dist_vmaf][dist_ssim][dist_psnr]; "
        "[dist_vmaf][ref_vmaf]libvmaf=model=version=vmaf_v0.6.1:"
        f"n_threads={thread_limit}:n_subsample=16; "
        "[dist_ssim][ref_ssim]ssim; "
        "[dist_psnr][ref_psnr]psnr"
    )

    # directly capture output to avoid writing to a log file or missing capturing output from buffered processes
    stderr_accumulator = []

    cmd = [
        # prefixed with 'nice -n 19' to prevent CPU starvation.
        # lowers processing priority so it never freezes the container's main web app loop
        "nice", "-n", "19",
        ffmpeg_path, "-y",
        "-threads", f"{thread_limit}", "-i", original,
        "-threads", f"{thread_limit}", "-i", reencoded,
        "-filter_complex", filter_complex,
        "-progress", "pipe:2",
        "-f", "null", "-"
    ]

    print(f"Analyzing video quality... ({thread_limit} threads available)")
    print(f"FFmpeg command:\n{' '.join(cmd)}\n")

    # Initialize progress tracking based on whether tqdm is available
    if HAS_TQDM:
        pbar = tqdm(total=total_frames, unit="frame", desc="Processing Frames")
    else:
        print(f"Tracking progress for {total_frames} frames...", flush=True)

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    # Matches: SSIM Y:0.904232 (10.187793) U:0.983563 (17.841855) V:0.979118 (16.802351) All:0.929935 (11.544983)
    ssim_regex = re.compile(r"SSIM\sY:([0-9.]+)\s\([0-9.]+\)\sU:([0-9.]+)\s\([0-9.]+\)\sV:([0-9.]+)\s\([0-9.]+\)\sAll:([0-9.]+)")
    # Matches: [Parsed_libvmaf_2 @ 0x799fd8006fc0] VMAF score: 40.932416
    vmaf_regex = re.compile(r"VMAF\sscore:\s([0-9.]+)")
    # Matches: PSNR y:23.907860 u:40.097852 v:39.062022 average:25.609931 min:4.257444 max:96.790130
    psnr_regex = re.compile(r"PSNR\s+y:([0-9.]+)\su:([0-9.]+)\sv:([0-9.]+)\saverage:([0-9.]+)\smin:([0-9.]+)\smax:([0-9.]+)")
    results = {}

    for line in iter(process.stderr.readline, ""):
        # Save error track line down accumulator array for diagnostics if it fails
        stderr_accumulator.append(line)

        if not line or line == "":
            continue

        # 1. High-Speed Progress Filter (Executes thousands of times)
        #    - Only update the visual UI bar every so often to avoid waiting to write to the terminal
        if line.startswith("frame="):
            try:
                # Optimized string splitting to avoid heavy regex parsing for progress
                current_frame = int(line.split("=")[1].split()[0].strip())

                if HAS_TQDM:
                    pbar.n = current_frame
                    pbar.refresh()
                elif total_frames:
                    # Docker/Text mode: Log progress at every 10% milestone
                    current_pct = int((current_frame / total_frames) * 100)
                    print(f"Processing progress: {current_pct}% ({current_frame}/{total_frames} frames)", flush=True)
            except (IndexError, ValueError):
                pass
            continue
        # stats are printed after this line, ensure we do not exit early!
        # elif line.startswith("progress=end"):
        #     break

        # 2. Gatekeeper Filters: Only run heavy regex matchers if keywords exist on the line
        if "SSIM " in line:
            ssim_match = ssim_regex.search(line)
            if ssim_match:
                results["ssim_global"] = float(ssim_match.group(4))
                results["ssim_y"] = float(ssim_match.group(1))
                results["ssim_cb"] = float(ssim_match.group(2))
                results["ssim_cr"] = float(ssim_match.group(3))
                continue

        if "VMAF score" in line:
            vmaf_match = vmaf_regex.search(line)
            if vmaf_match:
                results["vmaf"] = float(vmaf_match.group(1))
                continue

        if "PSNR " in line:
            psnr_match = psnr_regex.search(line)
            if psnr_match:
                results["psnr_y"] = float(psnr_match.group(1))
                results["psnr_u"] = float(psnr_match.group(2))
                results["psnr_v"] = float(psnr_match.group(3))
                results["psnr_average"] = float(psnr_match.group(4))
                results["psnr_min"] = float(psnr_match.group(5))
                results["psnr_max"] = float(psnr_match.group(6))
                continue

    if HAS_TQDM:
        pbar.close()

    process.wait()

    if process.returncode != 0:
        print("FFmpeg execution failed. Error details:")
        print("".join(stderr_accumulator[-30:]))
        print(f"\nFFmpeg process failed with exit code: {process.returncode}")
        sys.exit(1)
    else:
        print("FFmpeg execution success. Final logs:")
        print("".join(stderr_accumulator[-30:]))

    return results


def parse_results(output_log, min_vmaf, min_psnr, min_ssim):
    # Parse results from the generated log file
    try:
        with open(args.output_log, "r") as f:
            results = json.load(f)

            vmaf_score = results.get("vmaf")
            vmaf_pass = vmaf_score >= min_vmaf
            
            global_ssim = results.get('ssim_global')
            ssim_pass = global_ssim >= min_ssim

            global_psnr = results.get('psnr_average')
            psnr_pass = global_psnr >= min_psnr

            print("=" * 40)
            print("        QUALITY COMPARISON RESULTS      ")
            print("=" * 40)
            print(f"VMAF Score: {vmaf_score:.2f} / 100")
            print(f"PSNR Score: {global_psnr:.2f} dB")
            print(f"SSIM Score: {global_ssim:.4f}")
            print("=" * 40)

            if vmaf_pass and psnr_pass and ssim_pass:
                print(f"Verdict: Pass. All metrics met or exceded the configured thresholds.")
            else:
                print("Verdict: Fail! One or more quality gates rejected the encode:")
                if not vmaf_pass:
                    print(
                        f"  - VMAF {vmaf_score:.2f} failed target of {min_vmaf:.1f}")
                if not psnr_pass:
                    print(
                        f"  - PSNR {global_psnr:.2f}dB failed target of {min_psnr:.1f}dB")
                if not ssim_pass:
                    print(
                        f"  - SSIM {global_ssim:.4f} failed target of {min_ssim:.4f}")
                print('\nFull stats:')
                pretty_json = json.dumps(results, indent=4)
                print(pretty_json)

    except Exception as e:
        print(f"Failed to parse metrics log file: {e}")


if __name__ == "__main__":
    args = parse_arguments()
    check_dependencies(args.ffmpeg_path)

    if (not args.parse_results):
        check_inputs(args.original, args.reencoded)
        results = analyze_video_similarity(
            args.original,
            args.reencoded,
            args.ffmpeg_path,
            args.output_log,
            args.threads
        )

        with open(args.output_log, "w", encoding="utf-8") as file:
            json.dump(results, file)

    parse_results(args.output_log, args.min_vmaf, args.min_psnr, args.min_ssim)
