#!/usr/bin/env python3
"""
ElevenLabs Voiceover Generation Script for Company Brain Demo
=============================================================

This script converts the 5-scene narration script for our 1080p HD demo video
into realistic studio-quality voiceover audio using ElevenLabs Text-to-Speech API.

Usage:
------
1. Set your ElevenLabs API key:
   export ELEVENLABS_API_KEY="your-api-key-here"

2. Run the script:
   backend/.venv/bin/python backend/scripts/generate_voiceover_elevenlabs.py

Options:
--------
  --voice-id VOICE_ID     ElevenLabs Voice ID (default: pNInz6obpgDQGcFmaJgB - Adam)
  --output-dir DIR        Directory to save generated audio (default: ./voiceover_output)
  --merge-video VIDEO     Multiplex audio into video using ffmpeg (e.g. company_brain_demo.mp4)
  --dry-run               Print narration script and duration estimates without calling API
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path

# Scene Narration Script synchronized with the 5 demo scenes
SCENES = [
    {
        "scene": 1,
        "title": "Architecture & Live FalkorDB Topology",
        "timestamp": "0:00 - 0:15",
        "duration_target": "15s",
        "text": (
            "Welcome to Company Brain, our hackathon submission for Graph Hacks. "
            "Company Brain unifies fragmented enterprise knowledge across documents, tickets, team chats, "
            "and architecture decisions into a single high-performance FalkorDB knowledge graph. "
            "As shown in the live topology, entities like the payment gateway, authorization RFCs, "
            "and engineering leads are connected with real-time multi-hop graph semantics—powered "
            "directly by FalkorDB on port 6379."
        ),
    },
    {
        "scene": 2,
        "title": "Tracing Decisions Back to Clear Sources",
        "timestamp": "0:15 - 0:35",
        "duration_target": "20s",
        "text": (
            "When asking why an architecture decision was made, Company Brain does not hallucinate. "
            "It traverses the FalkorDB graph to trace decisions back to their exact historical sources. "
            "Here, the payment gateway authentication change is linked directly to a high-priority incident "
            "discussion in Slack channel inc-payments and Linear ticket PAY-402. "
            "Every claim is strictly grounded and verified against a SHA-256 cryptographic content hash "
            "in the evidence drawer."
        ),
    },
    {
        "scene": 3,
        "title": "Who Owns What vs. Who Knows What",
        "timestamp": "0:35 - 0:50",
        "duration_target": "15s",
        "text": (
            "Next, Company Brain resolves the critical enterprise distinction between formal ownership "
            "and subject matter expertise. In the inspector, Priya Nair is identified as the active owner "
            "with formal accountability via the OWNS relationship. "
            "Simultaneously, FalkorDB calculates subject matter expertise dynamically from authored decisions, "
            "tickets, and incident responses—ranking Aarav Mehta and Rohan Verma as the leading technical experts."
        ),
    },
    {
        "scene": 4,
        "title": "Detecting Documentation Drift & Atomic CAS Mutation",
        "timestamp": "0:50 - 1:10",
        "duration_target": "20s",
        "text": (
            "Over time, documentation drifts from code and production reality. "
            "Company Brain detects that the Payments Auth RFC is stale and out of sync with current "
            "Ed25519 authentication decisions. It stages a mutation proposal diff with calculated "
            "blast radius and divergence hops. When confirmed, FalkorDB commits an atomic, "
            "two-phase CAS graph update, marking the document aligned with zero database conflict."
        ),
    },
    {
        "scene": 5,
        "title": "Strict Multi-Tenant Graph Isolation",
        "timestamp": "1:10 - 1:33",
        "duration_target": "23s",
        "text": (
            "Finally, enterprise security demands strict multi-tenant isolation. "
            "Switching tenant context from Acme Payments to Nexus Infra immediately reloads an isolated "
            "Kafka and KRaft consensus topology. With zero cross-tenant data leakage and hard cryptographic "
            "boundaries, Company Brain demonstrates autonomous, enterprise-grade knowledge architecture "
            "powered by FalkorDB."
        ),
    },
]

DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam (Deep, articulate narrator)
MODEL_ID = "eleven_multilingual_v2"


def estimate_duration_seconds(text: str) -> float:
    """Rough estimation based on 150 words per minute average speaking rate."""
    words = len(text.split())
    return round((words / 150.0) * 60.0, 1)


def generate_audio_elevenlabs(text: str, voice_id: str, api_key: str, output_path: Path):
    """Call ElevenLabs REST API to convert text to speech MP3."""
    import httpx

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.50,
            "similarity_boost": 0.78,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }

    response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
    if response.status_code != 200:
        raise RuntimeError(
            f"ElevenLabs API Error (HTTP {response.status_code}): {response.text}"
        )

    output_path.write_bytes(response.content)
    print(f"  -> Saved audio ({len(response.content) / 1024:.1f} KB): {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate ElevenLabs voiceover for demo video")
    parser.add_argument("--api-key", default=os.getenv("ELEVENLABS_API_KEY"), help="ElevenLabs API Key")
    parser.add_argument("--voice-id", default=os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID), help="Voice ID")
    parser.add_argument("--output-dir", default="./voiceover_output", help="Directory for audio outputs")
    parser.add_argument("--merge-video", default=None, help="Path to video file to merge audio into")
    parser.add_argument("--dry-run", action="store_true", help="Print narration without calling API")
    args = parser.parse_args()

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("==================================================================")
    print("  ElevenLabs Voiceover Generator — Company Brain Demo (1080p HD)  ")
    print("==================================================================")
    print(f"Voice ID:    {args.voice_id}")
    print(f"Model ID:    {MODEL_ID}")
    print(f"Output Dir:  {out_dir}\n")

    full_transcript = []

    for scene in SCENES:
        s_num = scene["scene"]
        s_title = scene["title"]
        s_time = scene["timestamp"]
        s_text = scene["text"]
        words = len(s_text.split())
        est_sec = estimate_duration_seconds(s_text)

        print(f"Scene {s_num}: {s_title} [{s_time}]")
        print(f"  Target: {scene['duration_target']} | Est: {est_sec}s | Words: {words}")
        print(f'  Script: "{s_text[:85]}..."')
        full_transcript.append(f"--- Scene {s_num}: {s_title} ({s_time}) ---\n{s_text}\n")

    # Save full transcript for convenience
    script_txt_path = out_dir / "voiceover_transcript.txt"
    script_txt_path.write_text("\n".join(full_transcript), encoding="utf-8")
    print(f"\n[Saved] Full narration text saved to: {script_txt_path}")

    if args.dry_run:
        print("\n[Dry Run] Done. To generate audio, provide ELEVENLABS_API_KEY and run without --dry-run.")
        return

    if not args.api_key:
        print("\n[Notice] No ELEVENLABS_API_KEY detected.")
        print("To generate speech with ElevenLabs, set the environment variable:")
        print("  export ELEVENLABS_API_KEY=\"your_key_here\"")
        print("  python backend/scripts/generate_voiceover_elevenlabs.py")
        print("\nYou can also copy 'voiceover_transcript.txt' into ElevenLabs web studio directly.")
        return

    # Generate individual scene audios
    scene_files = []
    print("\nCalling ElevenLabs API to synthesize audio for each scene...")
    for scene in SCENES:
        s_num = scene["scene"]
        scene_mp3 = out_dir / f"scene_{s_num}.mp3"
        print(f"Generating Scene {s_num} audio...")
        generate_audio_elevenlabs(scene["text"], args.voice_id, args.api_key, scene_mp3)
        scene_files.append(scene_mp3)

    # Generate continuous master voiceover track
    full_text = " ... ".join([s["text"] for s in SCENES])
    master_mp3 = out_dir / "voiceover_master.mp3"
    print("\nGenerating full master voiceover track...")
    generate_audio_elevenlabs(full_text, args.voice_id, args.api_key, master_mp3)

    # Optional: Merge into video using ffmpeg
    video_target = args.merge_video or ("company_brain_demo.mp4" if Path("company_brain_demo.mp4").exists() else None)
    if video_target and Path(video_target).exists():
        merged_output = Path(video_target).with_name(f"{Path(video_target).stem}_with_voiceover.mp4")
        print(f"\n[FFmpeg] Merging audio '{master_mp3}' into video '{video_target}' -> '{merged_output}'...")
        try:
            cmd = [
                "/opt/homebrew/bin/ffmpeg", "-y",
                "-i", str(video_target),
                "-i", str(master_mp3),
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                str(merged_output),
            ]
            subprocess.run(cmd, check=True)
            print(f"[Success] Created video with voiceover: {merged_output}")
        except Exception as e:
            print(f"[Warning] Failed to merge audio with video: {e}")

    print("\n[Done] ElevenLabs voiceover generation process completed!")


if __name__ == "__main__":
    main()
