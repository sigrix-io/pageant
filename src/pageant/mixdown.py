"""A silent lesson's sound: the narration, a click for each click, and the music under them.

Each narration clip is levelled to the same loudness and starts where its caption appears;
the music (``music.py``) ducks under the voice, about 10 dB under it in a pause and about
15 dB under it while it speaks. The mix is then set to the lesson's loudness in two passes
(``loudness.py``): -16 LUFS, the level web players expect, unless the lesson says otherwise,
its peaks kept 2 dB under full scale, and muxed beside the untouched picture.
"""

from __future__ import annotations

import subprocess
import wave
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from pageant import loudness, music

RATE = 48_000
VOICE_RMS_DB = -20.0

#: The music's level, and how far the voice ducks it: the narration, the music and the clicks, in that order.
GRAPH = (
    "[0:a]aformat=sample_fmts=fltp:channel_layouts=stereo,asplit=2[voice][key];"
    "[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.14[bed];"
    "[bed][key]sidechaincompress=threshold=0.05:ratio=4:attack=40:release=700[ducked];"
    "[2:a]aformat=sample_fmts=fltp:channel_layouts=stereo[click];"
    "[voice][ducked][click]amix=inputs=3:normalize=0:duration=first[mix]"
)


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as clip:
        rate, channels = clip.getframerate(), clip.getnchannels()
        data = np.frombuffer(clip.readframes(clip.getnframes()), "<i2").astype(np.float64) / 32768
    return data.reshape(-1, channels).mean(axis=1), rate


def write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(pcm.tobytes())


def resample(audio: np.ndarray, source: int) -> np.ndarray:
    """Band-limited resampling to 48 kHz by FFT: enough for speech made at 24 kHz."""

    if source == RATE:
        return audio
    n = round(len(audio) * RATE / source)
    return np.asarray(np.fft.irfft(np.fft.rfft(audio), n) * (n / len(audio)))


def click_sound(release: bool, rng: np.random.Generator) -> np.ndarray:
    """A soft mouse click: a short tick and a damped blip, a little lower and quieter on release."""

    t = np.arange(int(0.035 * RATE)) / RATE
    tick = rng.standard_normal(len(t)) * np.exp(-t / 0.0015)
    blip = np.sin(2 * np.pi * (1500 if release else 1900) * t) * np.exp(-t / 0.005)
    sound = np.diff(0.5 * tick + blip, prepend=0.0)
    return np.asarray(sound / np.abs(sound).max() * (0.10 if release else 0.16))


def place(track: np.ndarray, sound: np.ndarray, at: float) -> None:
    start = int(max(0.0, at) * RATE)
    end = min(len(track), start + len(sound))
    if end > start:
        track[start:end] += sound[: end - start]


def mix(
    voice: Sequence[tuple[float, Path]],
    clicks: Sequence[float],
    seconds: float,
    picture: Path,
    out: Path,
    work: Path,
    target: float = loudness.WEB,
) -> None:
    """``out``: ``picture`` with the narration clips at their times, the clicks, and the music, at ``target`` LUFS."""

    total = int(seconds * RATE) + RATE
    narration = np.zeros(total)
    for at, file in voice:
        clip, rate = read_wav(file)
        clip = resample(clip, rate)
        clip *= 10 ** (VOICE_RMS_DB / 20) / (np.sqrt(np.mean(clip**2)) or 1.0)
        place(narration, clip, at)
    rng = np.random.default_rng(3)
    clicking = np.zeros(total)
    for at in clicks:
        place(clicking, click_sound(False, rng), at)
        place(clicking, click_sound(True, rng), at + 0.07)
    write_wav(work / "narration.wav", narration)
    write_wav(work / "clicks.wav", clicking)
    music.write(work / "music.wav", seconds + 1)
    mixed = work / "mix.wav"
    # Kept in floating point until it is levelled, so a sum over full scale is not clipped first.
    ffmpeg(
        *("-i", str(work / "narration.wav"), "-i", str(work / "music.wav"), "-i", str(work / "clicks.wav")),
        *("-filter_complex", GRAPH, "-map", "[mix]", "-c:a", "pcm_f32le", str(mixed)),
    )
    report = ffmpeg_report("-i", str(mixed), "-af", loudness.first_pass(target), "-f", "null", "-")
    level = loudness.second_pass(target, loudness.measured(report))
    ffmpeg(
        *("-i", str(picture), "-i", str(mixed), "-af", f"{level},aresample=48000"),
        *("-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"),
        *("-shortest", "-movflags", "+faststart", str(out)),
    )


def ffmpeg(*arguments: str) -> None:
    """Run ffmpeg quietly, overwriting its output; a failure raises, with what ffmpeg said."""

    _run("error", arguments)


def ffmpeg_report(*arguments: str) -> str:
    """Run ffmpeg and answer what it reported, which is where a measuring filter prints what it found."""

    return _run("info", arguments)


def _run(level: str, arguments: Sequence[str]) -> str:
    done = subprocess.run(  # noqa: S603 -- ffmpeg, with arguments these modules spell
        ["ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", level, *arguments],  # noqa: S607 -- the ffmpeg on PATH
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {done.stderr.strip()}")
    return done.stderr
