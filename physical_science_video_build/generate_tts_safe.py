from __future__ import annotations

import asyncio
import json
import ssl
from pathlib import Path

import edge_tts
import edge_tts.communicate as communicate_module

VOICE = "en-IN-NeerjaNeural"
RATE = "-8%"
PITCH = "-2Hz"
OUT = Path("physical_science_english_tts")
SOURCE = Path("physical_science_video_build/lessons.json")


async def synthesize(text: str, audio_path: Path, words_path: Path) -> dict:
    communication = edge_tts.Communicate(
        text, VOICE, rate=RATE, pitch=PITCH, boundary="WordBoundary"
    )
    words = []
    with audio_path.open("wb") as handle:
        async for chunk in communication.stream():
            if chunk["type"] == "audio":
                handle.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append(
                    {
                        "text": chunk["text"],
                        "start": round(chunk["offset"] / 10_000_000, 4),
                        "end": round(
                            (chunk["offset"] + chunk["duration"]) / 10_000_000,
                            4,
                        ),
                    }
                )
    if audio_path.stat().st_size < 1000 or not words:
        raise RuntimeError(f"Invalid synthesis output: {audio_path}")
    words_path.write_text(
        json.dumps({"text": text, "words": words}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "audio": audio_path.name,
        "words": words_path.name,
        "word_count": len(words),
        "audio_size_bytes": audio_path.stat().st_size,
    }


async def main() -> None:
    communicate_module._SSL_CTX = ssl.create_default_context()
    lessons = json.loads(SOURCE.read_text(encoding="utf-8"))
    if len(lessons) != 21:
        raise RuntimeError(f"Expected 21 lessons, found {len(lessons)}")
    OUT.mkdir(parents=True, exist_ok=True)
    course = {
        "voice": VOICE,
        "rate": RATE,
        "pitch": PITCH,
        "lesson_count": 21,
        "lessons": [],
    }
    for lesson in lessons:
        number = int(lesson["number"])
        beats = lesson["beats"]
        if len(beats) != 6 or beats[0]["start"] != 0 or beats[-1]["end"] != 120:
            raise RuntimeError(f"Invalid structure in lesson {number}")
        for left, right in zip(beats, beats[1:]):
            if left["end"] != right["start"]:
                raise RuntimeError(f"Timing discontinuity in lesson {number}")
        folder = OUT / f"lesson_{number:02d}"
        folder.mkdir(exist_ok=True)
        out_lesson = {
            "number": number,
            "title": lesson["title"],
            "duration": 120,
            "beats": [],
        }
        for beat in beats:
            out_beat = {
                "index": beat["index"],
                "name": beat["name"],
                "start": beat["start"],
                "end": beat["end"],
                "events": [],
            }
            for event_number, event in enumerate(beat["events"], start=1):
                record = {
                    "index": event_number,
                    "type": event["type"],
                    "text": event.get("text", ""),
                }
                if event["type"] == "hold":
                    duration = float(event["duration"])
                    if duration not in (3.0, 4.0):
                        raise RuntimeError(
                            f"Invalid hold in lesson {number}, beat {beat['index']}"
                        )
                    record["duration"] = duration
                elif event["type"] == "voiceover":
                    stem = f"beat_{int(beat['index']):02d}_event_{event_number:02d}"
                    record.update(
                        await synthesize(
                            event["text"],
                            folder / f"{stem}.mp3",
                            folder / f"{stem}_words.json",
                        )
                    )
                else:
                    raise RuntimeError(f"Unknown event type: {event['type']}")
                out_beat["events"].append(record)
            out_lesson["beats"].append(out_beat)
        (folder / "lesson_manifest.json").write_text(
            json.dumps(out_lesson, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        course["lessons"].append(out_lesson)
        print(f"Completed lesson {number:02d}", flush=True)
    (OUT / "course_manifest.json").write_text(
        json.dumps(course, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
