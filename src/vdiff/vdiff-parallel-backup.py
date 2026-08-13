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


# TODO: [ ] confirm linear fallback mode
# TODO: [ ] test with different number of workers provisioned
# TODO: [ ] TQDM fallback/disable within docker containers
# TODO: [ ] time container alignment to reduce processing overhead
# TODO: [ ] testing! 

import concurrent.futures
import subprocess
import json
import os
import sys
import argparse
import math
import re
import socket
import fcntl
import time


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
    #  HEVC processing recommendeds 16 threads
    default_cores = 8
    default_workers = 2

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
        "-c", "--max-cores",
        type=int,
        default=default_cores,
        help="Maximum number of cores to utilise during processing."
    )
    parser.add_argument(
        "-w", "--num-workers",
        type=int,
        default=default_workers,
        help="Maximum number of workers to assign to the processing. Cores (threads) will be distributed to workers if processing in parallel."
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


def analyze_video_segment(original, reencoded, ffmpeg_path, start_time, duration, worker_id, thread_limit):
    """
    Processes a precise timestamped segment window of the video asset.
    """

    # Use the fast shared-memory RAM disk folder on Linux (/dev/shm) to store status lines.
    # This prevents physical disk read/write slowdowns.
    progress_file = f"/dev/shm/ffmpeg_p_worker_{worker_id}.txt"

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

    # Fast seek (-ss) applied BEFORE inputs tells FFmpeg to discard and skip frames instantly
    cmd = [
        "nice", "-n", "19",
        ffmpeg_path, "-y",
        "-ss", f"{start_time:.3f}", "-t", f"{duration:.3f}", "-threads", str(
            thread_limit), "-i", original,
        "-ss", f"{start_time:.3f}", "-t", f"{duration:.3f}", "-threads", str(
            thread_limit), "-i", reencoded,
        "-filter_complex", filter_complex,
        "-progress", progress_file,
        "-f", "null", "-",
    ]

    return subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    ), progress_file


def analyze_video_similarity_parallel(original, reencoded, ffmpeg_path, output_log, max_cores=32, num_workers=4):
    """
    Computes VMAF, PSNR, and SSIM between the original and lossy re-encoded video.
    Filters sync the videos by scaling the re-encoded file to match the original dimensions.

    Divides the video into segments and processes them concurrently.
    """

    total_duration = get_video_duration(original, ffmpeg_path)
    if not total_duration:
        print("Error: Could not determine video duration. Falling back to linear mode.")
        return None

    total_frames = get_total_frames(original, ffmpeg_path)
    if not total_frames:
        print("Warning: Could not determine total frame count. Progress bar will tracking cannot be determined for parallel processing. Falling back to linear mode.")
        return None

    # Balance workers: Assign a safe subset of threads per active worker process
    threads_per_worker = max(1, math.floor(max_cores / num_workers))
    segment_duration = total_duration / num_workers
    frames_per_worker = math.ceil(total_frames / num_workers)

    print(f"Analyzing: \n  Original: {original}\n  Re-encoded: {reencoded}\n")
    print("Running quality metrics via FFmpeg (this may take a few minutes)...")
    print(
        f"Spawning {num_workers} parallel workers processing {segment_duration:.2f}s segments concurrently...")

    # Track progress with dynamic dictionary of distinct visual tqdm bars stacked vertically
    active_workers = {}
    pbars = {}

    for w_id in range(num_workers):
        start_time = w_id * segment_duration
        proc, prog_file = analyze_video_segment(
            original,
            reencoded,
            ffmpeg_path,
            start_time,
            segment_duration,
            w_id,
            threads_per_worker,
        )
        # Store all process metadata inside a tracking object
        active_workers[w_id] = {
            "process": proc,
            "prog_file": prog_file,
            "stderr_accumulator": [],
            "done": False,
        }
        pbars[w_id] = tqdm(
            total=frames_per_worker,
            position=w_id,
            leave=False,
            unit="frame",
            desc=f"Worker #{w_id}",
        )

    while True:
        still_running = False
        time.sleep(0.2)  # Balanced loop interval

        for w_id, info in active_workers.items():
            if info["done"]:
                continue

            proc = info["process"]

            # NON-BLOCKING READ: Continuously empty the stderr buffer to prevent deadlocks
            # Setting up non-blocking flags or checking readable states protects the pipeline
            try:
                # Read whatever data is currently waiting in the OS pipeline buffer
                # Using read(4096) prevents blocking if the pipe is temporarily empty
                fd = proc.stderr.fileno()
                fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

                chunk = proc.stderr.read(4096)
                if chunk:
                    info["stderr_accumulator"].append(chunk)
            except (IOError, TypeError):
                pass  # Pipe is temporarily empty, skip reading

            # Update the progress bar using the RAM storage file
            p_file = info["prog_file"]
            if os.path.exists(p_file):
                try:
                    with open(p_file, "r") as f:
                        content = f.read()
                    frame_matches = re.findall(r"frame=(\d+)", content)
                    if frame_matches:
                        pbars[w_id].n = int(frame_matches[-1])
                        pbars[w_id].refresh()
                except (IOError, ValueError):
                    pass

            # Check if this specific worker has finished running
            if proc.poll() is not None:
                # Read any remaining data left in the pipe before closing it down
                try:
                    final_chunk = proc.stderr.read()
                    if final_chunk:
                        info["stderr_accumulator"].append(final_chunk)
                except Exception:
                    pass

                pbars[w_id].close()
                info["done"] = True

                # Clean up the progress file from RAM immediately
                if os.path.exists(p_file):
                    try:
                        os.remove(p_file)
                    except OSError:
                        pass
            else:
                still_running = True

        # Break out of the loop once all workers have finished processing
        if not still_running:
            break

    # TODO: needed?
    # Clean up the console layout to prevent overlapping terminal text strings
    # print("\n" * num_workers)

    # 3. Post-Process Metric Parsing
    segment_results = []
    for w_id, info in active_workers.items():
        full_text = "".join(info["stderr_accumulator"])
        metrics = parse_final_stderr(full_text)
        if metrics:
            segment_results.append(metrics)

    # 4. Calculate final weighted averages
    valid_chunks = [r for r in segment_results if "vmaf" in r]
    if not valid_chunks:
        print("[!] Error: All parallel segment workers failed to return data.")
        return {}

    final_results = {
        "ssim_global": sum(c["ssim_global"] for c in valid_chunks)
        / len(valid_chunks),
        "ssim_y": sum(c["ssim_y"] for c in valid_chunks) / len(valid_chunks),
        "ssim_cb": sum(c["ssim_cb"] for c in valid_chunks) / len(valid_chunks),
        "ssim_cr": sum(c["ssim_cr"] for c in valid_chunks) / len(valid_chunks),
        "vmaf": sum(c["vmaf"] for c in valid_chunks) / len(valid_chunks),
        "psnr_y": sum(c["psnr_y"] for c in valid_chunks) / len(valid_chunks),
        "psnr_average": sum(c["psnr_average"] for c in valid_chunks)
        / len(valid_chunks),
    }

    print("[+] Parallel analysis complete.")
    return final_results


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

    # Bind an ephemeral TCP loopback socket on the host machine to catch progress bytes
    # this avoids spamming stdout/stderr streams with fast progress updates
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 0 automatically picks any free open port
    server_socket.bind(('127.0.0.1', 0))
    port = server_socket.getsockname()[1]
    server_socket.listen(1)

    cmd = [
        # prefixed with 'nice -n 19' to prevent CPU starvation.
        # lowers processing priority so it never freezes the container's main web app loop
        "nice", "-n", "19",
        ffmpeg_path, "-y",
        "-threads", f"{thread_limit}", "-i", original,
        "-threads", f"{thread_limit}", "-i", reencoded,
        "-filter_complex", filter_complex,
        # eliminate progress tracking via stdio streams to improve FPS performance
        # instead push to this socket
        "-progress", f"tcp://127.0.0.1:{port}",
        "-f", "null", "-"
    ]

    print(
        f"Ephemeral TCP socket instantiated to resolve progress. Listening at 127.0.0.1:{port}")

    print(f"Analyzing video quality... ({thread_limit} threads available)")
    print(f"FFmpeg command:\n{' '.join(cmd)}\n")

    if HAS_TQDM and total_frames:
        pbar = tqdm(total=total_frames, unit="frame", desc="Processing")
    else:
        print("Processing at maximum speed...", flush=True)

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Accept the incoming connection from FFmpeg's progress engine
    conn, addr = server_socket.accept()

    # Fast number extractor for raw progress bytes
    frame_matcher = re.compile(r"frame=(\d+)")

    # keep processing entirely in-memory to improve perf
    # avoid any reading to/from stdio streams and instead resolve directly from the loopback interface
    with conn:
        while True:
            try:
                data = conn.recv(4096)
                if not data:
                    break

                # Convert the byte block to text and grab the latest frame number
                text_chunk = data.decode('utf-8', errors='ignore')
                matches = frame_matcher.findall(text_chunk)
                if matches and HAS_TQDM and total_frames:
                    # Update the progress bar to match the latest frame count
                    pbar.n = int(matches[-1])
                    pbar.refresh()
            except socket.timeout:
                # Break out of the loop if FFmpeg unexpectedly crashes or stops sending data
                print("\n[!] Socket timed out waiting for progress updates.")
                break

    if HAS_TQDM and total_frames:
        pbar.close()
    server_socket.close()

    # Gather everything from stderr at the very end
    stderr_data = process.stderr.read()
    process.wait()
    stderr_lines = stderr_data.splitlines()

    if process.returncode != 0:
        print("FFmpeg execution failed. Error details:")
        print("".join(stderr_lines[-30:]))
        print(f"\nFFmpeg process failed with exit code: {process.returncode}")
        sys.exit(1)
    else:
        print("FFmpeg execution success. Final logs:")
        print("".join(stderr_lines[-30:]))

    return parse_metrics_from_stream(stderr_lines)


def parse_final_stderr(stderr_text):
    """Scrapes the final quality metrics from a completed segment's text dump."""
    ssim_regex = re.compile(
        r"SSIM\sY:([0-9.]+)\s\([0-9.]+\)\sU:([0-9.]+)\s\([0-9.]+\)\sV:([0-9.]+)\s\([0-9.]+\)\sAll:([0-9.]+)"
    )
    vmaf_regex = re.compile(r"VMAF\sscore:\s([0-9.]+)")
    psnr_regex = re.compile(
        r"PSNR\s+y:([0-9.]+)\su:([0-9.]+)\sv:([0-9.]+)\saverage:([0-9.]+)"
    )

    metrics = {}
    for line in stderr_text.splitlines()[-50:]:
        if "SSIM " in line:
            m = ssim_regex.search(line)
            if m:
                metrics["ssim_global"] = float(m.group(4))
                metrics["ssim_y"] = float(m.group(1))
                metrics["ssim_cb"] = float(m.group(2))
                metrics["ssim_cr"] = float(m.group(3))
        if "VMAF score" in line:
            m = vmaf_regex.search(line)
            if m:
                metrics["vmaf"] = float(m.group(1))
        if "PSNR " in line:
            m = psnr_regex.search(line)
            if m:
                metrics["psnr_y"] = float(m.group(1))
                metrics["psnr_average"] = float(m.group(4))
    return metrics


def parse_metrics_from_stream(stream):
    # Matches: SSIM Y:0.904232 (10.187793) U:0.983563 (17.841855) V:0.979118 (16.802351) All:0.929935 (11.544983)
    ssim_regex = re.compile(
        r"SSIM\sY:([0-9.]+)\s\([0-9.]+\)\sU:([0-9.]+)\s\([0-9.]+\)\sV:([0-9.]+)\s\([0-9.]+\)\sAll:([0-9.]+)")
    # Matches: [Parsed_libvmaf_2 @ 0x799fd8006fc0] VMAF score: 40.932416
    vmaf_regex = re.compile(r"VMAF\sscore:\s([0-9.]+)")
    # Matches: PSNR y:23.907860 u:40.097852 v:39.062022 average:25.609931 min:4.257444 max:96.790130
    psnr_regex = re.compile(
        r"PSNR\s+y:([0-9.]+)\su:([0-9.]+)\sv:([0-9.]+)\saverage:([0-9.]+)\smin:([0-9.]+)\smax:([0-9.]+)")
    results = {}

    # Scan only the final 50 summary lines from stderr instead of thousands of frame rows
    for line in stderr_lines[-50:]:
        if "SSIM " in line:
            ssim_match = ssim_regex.search(line)
            if ssim_match:
                results["ssim_global"] = float(ssim_match.group(4))
                results["ssim_y"] = float(ssim_match.group(1))
                results["ssim_cb"] = float(ssim_match.group(2))
                results["ssim_cr"] = float(ssim_match.group(3))

        if "VMAF score" in line:
            vmaf_match = vmaf_regex.search(line)
            if vmaf_match:
                results["vmaf"] = float(vmaf_match.group(1))

        if "PSNR " in line:
            psnr_match = psnr_regex.search(line)
            if psnr_match:
                results["psnr_y"] = float(psnr_match.group(1))
                results["psnr_u"] = float(psnr_match.group(2))
                results["psnr_v"] = float(psnr_match.group(3))
                results["psnr_average"] = float(psnr_match.group(4))
                results["psnr_min"] = float(psnr_match.group(5))
                results["psnr_max"] = float(psnr_match.group(6))

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
                print(
                    f"Verdict: Pass. All metrics met or exceded the configured thresholds.")
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

        results = analyze_video_similarity_parallel(
            args.original,
            args.reencoded,
            args.ffmpeg_path,
            args.output_log,
            args.max_cores,
            args.num_workers
        )

        if results is None:
            results = analyze_video_similarity(
                args.original,
                args.reencoded,
                args.ffmpeg_path,
                args.output_log,
                args.num_workers
            )

        with open(args.output_log, "w", encoding="utf-8") as file:
            json.dump(results, file)

    parse_results(args.output_log, args.min_vmaf, args.min_psnr, args.min_ssim)
