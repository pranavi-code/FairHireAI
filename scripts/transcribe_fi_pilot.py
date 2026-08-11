import argparse
import json
import statistics
import time
from pathlib import Path

import torch
import whisper_timestamped as whisper

parser = argparse.ArgumentParser()
parser.add_argument("--pilot-root", required=True)
parser.add_argument("--model-root", required=True)
parser.add_argument("--model", default="small.en")
args = parser.parse_args()

if not torch.cuda.is_available():
    raise RuntimeError("CUDA is unavailable; GPU transcription is required")

pilot_root = Path(args.pilot_root).resolve()
model_root = Path(args.model_root).resolve()
transcript_root = pilot_root / "transcripts"
transcript_root.mkdir(parents=True, exist_ok=True)
model_root.mkdir(parents=True, exist_ok=True)

pilot = json.loads((pilot_root / "pilot_10_manifest.json").read_text("utf-8"))

print("GPU:", torch.cuda.get_device_name(0))
print("Loading Whisper model:", args.model)

model = whisper.load_model(
    args.model,
    device="cuda",
    download_root=str(model_root),
)

summaries = []

for index, item in enumerate(pilot, start=1):
    audio = Path(item["normalized_audio"])
    output = transcript_root / f"{audio.stem}.json"

    print(f"[{index}/10] Transcribing {audio.name}")
    started = time.perf_counter()

    result = whisper.transcribe(
        model,
        str(audio),
        language="en",
        task="transcribe",
        fp16=True,
        temperature=0.0,
        beam_size=5,
        vad=False,
        compute_word_confidence=True,
        remove_empty_words=True,
        verbose=False,
    )

    clean_segments = []
    all_words = []
    previous_start = -1.0

    for segment in result.get("segments", []):
        words = []
        for word in segment.get("words", []):
            clean_word = {
                "text": word["text"].strip(),
                "start": float(word["start"]),
                "end": float(word["end"]),
                "confidence": float(word["confidence"]),
            }

            if not clean_word["text"]:
                continue
            if clean_word["start"] < previous_start - 0.05:
                raise RuntimeError(f"Non-monotonic timestamp in {audio.name}")
            if clean_word["end"] < clean_word["start"]:
                raise RuntimeError(f"Invalid word duration in {audio.name}")
            if not 0.0 <= clean_word["confidence"] <= 1.0:
                raise RuntimeError(f"Invalid confidence in {audio.name}")

            previous_start = clean_word["start"]
            words.append(clean_word)
            all_words.append(clean_word)

        clean_segments.append({
            "start": float(segment["start"]),
            "end": float(segment["end"]),
            "text": segment["text"].strip(),
            "confidence": float(segment.get("confidence", 0.0)),
            "no_speech_probability": float(segment.get("no_speech_prob", 0.0)),
            "words": words,
        })

    text = result.get("text", "").strip()
    if not text or not all_words:
        raise RuntimeError(f"Empty transcript for {audio.name}")

    elapsed = time.perf_counter() - started
    average_confidence = statistics.fmean(w["confidence"] for w in all_words)

    payload = {
        "video_id": item["video_id"],
        "interview_score": item["interview_score"],
        "model": args.model,
        "language": result.get("language", "en"),
        "text": text,
        "segments": clean_segments,
        "word_count": len(all_words),
        "average_word_confidence": average_confidence,
        "processing_seconds": elapsed,
    }

    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summaries.append({
        "video_id": item["video_id"],
        "words": len(all_words),
        "confidence": round(average_confidence, 4),
        "seconds": round(elapsed, 2),
        "text_preview": text[:100],
    })

    print(
        f"  words={len(all_words)}, "
        f"confidence={average_confidence:.4f}, time={elapsed:.2f}s"
    )

summary_file = transcript_root / "transcription_summary.json"
summary_file.write_text(json.dumps(summaries, indent=2), encoding="utf-8")

print(json.dumps(summaries, indent=2))
print("GPU peak memory GB:", round(torch.cuda.max_memory_allocated() / 1e9, 3))
print("WHISPER TRANSCRIPTION PASSED: 10/10")
