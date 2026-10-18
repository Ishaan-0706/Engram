#!/usr/bin/env python3
"""
Engram — Demo Video & Voiceover Merger
Combines the 1080p recorded demo video with ElevenLabs voiceover audio.
Supports scene-by-scene alignment or master track synchronization.
"""

import argparse
import os
import subprocess
from pathlib import Path


def merge_scene_audio(video_path: Path, output_path: Path, voiceover_dir: Path, offsets=None):
    if offsets is None:
        # Default calibrated start offsets in milliseconds
        # Scene 1: ~500ms, Scene 2: ~35000ms, Scene 3: ~68000ms, Scene 4: ~100000ms, Scene 5: ~131000ms
        offsets = [500, 35000, 68000, 100000, 131000]

    scene_files = [voiceover_dir / f"scene_{i}.mp3" for i in range(1, 6)]
    missing = [str(f) for f in scene_files if not f.exists()]

    if missing:
        print(f"[Warning] Missing scene audio files: {missing}")
        master_file = voiceover_dir / "voiceover_master.mp3"
        if master_file.exists():
            print(f"[Fallback] Using master track: {master_file}")
            merge_single_track(video_path, master_file, output_path)
            return
        else:
            raise FileNotFoundError(f"Neither scene files nor voiceover_master.mp3 found in {voiceover_dir}")

    print("==================================================================")
    print("           Engram — Synchronized Audio/Video Compositor           ")
    print("==================================================================")
    print(f"Video Input:  {video_path}")
    print(f"Video Output: {output_path}")
    print(f"Scene Files:  {[f.name for f in scene_files]}")
    print(f"Offsets (ms): {offsets}\n")

    filter_chains = []
    mix_inputs = []
    for i, offset in enumerate(offsets):
        filter_chains.append(f"[{i+1}:a]adelay={offset}|{offset}[a{i+1}]")
        mix_inputs.append(f"[a{i+1}]")

    mix_str = f"{''.join(mix_inputs)}amix=inputs={len(offsets)}:duration=longest:normalize=0[aout]"
    full_filter = f"{'; '.join(filter_chains)}; {mix_str}"

    ffmpeg_bin = "/opt/homebrew/bin/ffmpeg" if Path("/opt/homebrew/bin/ffmpeg").exists() else "ffmpeg"

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(video_path),
        "-i", str(scene_files[0]),
        "-i", str(scene_files[1]),
        "-i", str(scene_files[2]),
        "-i", str(scene_files[3]),
        "-i", str(scene_files[4]),
        "-filter_complex", full_filter,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]

    print("[FFmpeg] Running multi-channel delay and mix...")
    subprocess.run(cmd, check=True)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n[Success] Created synchronized video: {output_path} ({size_mb:.2f} MB)")


def merge_single_track(video_path: Path, audio_path: Path, output_path: Path, delay_ms: int = 500):
    ffmpeg_bin = "/opt/homebrew/bin/ffmpeg" if Path("/opt/homebrew/bin/ffmpeg").exists() else "ffmpeg"
    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", f"[1:a]adelay={delay_ms}|{delay_ms}[aout]",
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    print(f"[FFmpeg] Merging single audio track '{audio_path}' into '{video_path}'...")
    subprocess.run(cmd, check=True)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n[Success] Created merged video: {output_path} ({size_mb:.2f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Merge ElevenLabs voiceover with demo video")
    parser.add_argument("--video", default="company_brain_demo.mp4", help="Source video file path")
    parser.add_argument("--voiceover-dir", default="./voiceover_output", help="Directory with scene audio files")
    parser.add_argument("--output", default="company_brain_demo_with_voiceover.mp4", help="Output video file path")
    parser.add_argument("--use-master", action="store_true", help="Use single master voiceover file instead of scenes")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent
    video_path = Path(args.video)
    if not video_path.is_absolute():
        video_path = repo_root / video_path

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = repo_root / out_path

    voice_dir = Path(args.voiceover_dir)
    if not voice_dir.is_absolute():
        voice_dir = repo_root / voice_dir

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if args.use_master:
        master_audio = voice_dir / "voiceover_master.mp3"
        merge_single_track(video_path, master_audio, out_path)
    else:
        merge_scene_audio(video_path, out_path, voice_dir)


if __name__ == "__main__":
    main()
