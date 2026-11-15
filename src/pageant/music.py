"""A calm background bed for a lesson, synthesised here from nothing: no samples, nothing licensed.

    python -m pageant.music 40 bed.wav   # hear forty seconds of it

D major at 80 bpm, in sections of four chords, two bars each. The bed's own progression, Dmaj9,
Bm7, Gmaj7 and A(add9), opens it and comes back between three others in the key, so a lesson of
a few minutes does not hear the same 24 seconds come round again and again. A warm pad
throughout, a soft bass, and a quiet plucked arpeggio between the intro and the outro, which
takes a new figure each section and now and then rests for one, with a synthetic room over all
of it. 48 kHz stereo, peaking at -1 dBFS; mixdown.py ducks it under the voice. The same length
always gives the same track.
"""

from __future__ import annotations

import math
import random
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 48_000
BEAT = 60 / 80
CHORD_SECONDS = 8 * BEAT
SECTION_SECONDS = 4 * CHORD_SECONDS
#: Pad voicings, as MIDI notes, kept in one register so each change moves as little as it can.
CHORDS = {
    "Dmaj9": [50, 57, 61, 64, 66],  # D A C# E F#
    "Bm7": [47, 54, 57, 62, 66],  # B F# A D F#
    "Gmaj7": [55, 59, 62, 66, 69],  # G B D F# A
    "A(add9)": [52, 57, 59, 61, 64],  # E A B C# E
    "F#m7": [54, 57, 61, 64, 69],  # F# A C# E A
    "Em9": [52, 55, 59, 62, 66],  # E G B D F#
}
#: Each chord's root in the bass: D2, B1, G2, A2, F#2 and E2.
ROOTS = {"Dmaj9": 38, "Bm7": 35, "Gmaj7": 43, "A(add9)": 45, "F#m7": 42, "Em9": 40}
#: Each chord's arpeggio, an octave or two up: its root, third, fifth, and seventh or octave.
ARPEGGIOS = {
    "Dmaj9": [74, 78, 81, 85],
    "Bm7": [71, 74, 78, 81],
    "Gmaj7": [67, 71, 74, 78],
    "A(add9)": [69, 73, 76, 81],
    "F#m7": [66, 69, 73, 76],
    "Em9": [64, 67, 71, 74],
}
#: What a section can play, the bed's own progression first: the others each lead back to it.
PROGRESSIONS = [
    ("Dmaj9", "Bm7", "Gmaj7", "A(add9)"),
    ("Gmaj7", "A(add9)", "F#m7", "Bm7"),
    ("Em9", "Gmaj7", "Dmaj9", "A(add9)"),
    ("Bm7", "Gmaj7", "Em9", "A(add9)"),
]
#: The eighths of a bar the arpeggio sounds on, the bed's own first.
PATTERNS = [(1, 0, 1, 1, 0, 1, 0, 1), (1, 0, 0, 1, 0, 0, 1, 0), (1, 0, 1, 0, 1, 0, 1, 0), (1, 0, 0, 0, 1, 0, 1, 0)]
#: The order the arpeggio takes a chord's notes in, from the lowest; the bed's own, up and back, first.
SHAPES = [(0, 1, 2, 3, 2, 1), (0, 1, 2, 3), (0, 2, 1, 3), (3, 2, 1, 0)]


@dataclass(frozen=True)
class Section:
    """Eight bars of the bed: a progression's four chords, and the arpeggio's figure over them.

    ``pattern`` is ``None`` where the arpeggio rests for the section.
    """

    chords: tuple[str, ...]
    pattern: tuple[int, ...] | None
    shape: tuple[int, ...]


def plan(seconds: float) -> list[Section]:
    """The sections a bed of ``seconds`` plays: the same for the same length, and a longer bed
    begins with a shorter one's sections, so a lesson that grows keeps the music it had.

    The bed's own progression opens with its own figure, and comes back between each of the
    others, which go round in a shuffled order that does not start with the one that played last.
    Each section's figure is one its progression did not play its last two times, nor the section
    before it. After the first two sections, the arpeggio rests for one now and then, with at least
    two sections between rests.
    """

    generator = random.Random(7)  # noqa: S311 -- the music's choices, which only need to be the same each time

    def pick(count: int) -> int:
        # Only random() is held to the same sequence from one Python to the next, so every choice
        # comes from it, and in the order the sections play.
        return int(generator.random() * count)

    sections: list[Section] = []
    order: list[int] = []
    others: list[int] = []
    played: dict[int, list[tuple[int, int]]] = {}
    last: tuple[int, int] | None = None
    since = 2  # sections since the arpeggio last rested
    for index in range(max(1, math.ceil(seconds / SECTION_SECONDS))):
        if index % 2 == 0:
            progression = 0
        else:
            if not others:
                others = [1, 2, 3]
                for i in range(len(others) - 1, 0, -1):
                    j = pick(i + 1)
                    others[i], others[j] = others[j], others[i]
                if index > 1 and others[0] == order[-2]:
                    others.append(others.pop(0))
            progression = others.pop(0)
        figure = (0, 0)
        if index:
            spent = set(played.get(progression, [])[-2:]) | {last}
            free = [(p, s) for p in range(len(PATTERNS)) for s in range(len(SHAPES)) if (p, s) not in spent]
            figure = free[pick(len(free))]
        rest = index >= 2 and since >= 2 and generator.random() < 0.25
        pattern, shape = figure
        sections.append(Section(PROGRESSIONS[progression], None if rest else PATTERNS[pattern], SHAPES[shape]))
        order.append(progression)
        played.setdefault(progression, []).append(figure)
        last, since = figure, 0 if rest else since + 1
    return sections


def hz(note: float) -> float:
    return float(440.0 * 2 ** ((note - 69) / 12))


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    shape = np.ones(n)
    rise, fall = int(attack * RATE), int(release * RATE)
    shape[:rise] = np.sin(np.linspace(0, np.pi / 2, rise)) ** 2
    shape[n - fall :] *= np.cos(np.linspace(0, np.pi / 2, fall)) ** 2
    return shape


def pad_note(note: int, seconds: float, rng: np.random.Generator) -> np.ndarray:
    """One pad voice: three slightly detuned, softly bright oscillators across the stereo field."""

    t = np.arange(int(seconds * RATE)) / RATE
    out = np.zeros((len(t), 2))
    for cents, pan in ((-6, 0.25), (0, 0.5), (6, 0.75)):
        f = hz(note + cents / 100)
        phase = rng.uniform(0, 2 * np.pi)
        tone = sum(
            a * np.sin(2 * np.pi * f * k * t + k * phase) for k, a in ((1, 1.0), (2, 0.28), (3, 0.12), (4, 0.05))
        )
        out[:, 0] += tone * np.cos(pan * np.pi / 2)
        out[:, 1] += tone * np.sin(pan * np.pi / 2)
    return out / 3


def pluck(note: int, pan: float) -> np.ndarray:
    t = np.arange(int(1.6 * RATE)) / RATE
    f = hz(note)
    tone = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)) * np.exp(-t / 0.32)
    tone[: int(0.004 * RATE)] *= np.linspace(0, 1, int(0.004 * RATE))
    return np.stack([tone * np.cos(pan * np.pi / 2), tone * np.sin(pan * np.pi / 2)], axis=1)


def add(track: np.ndarray, part: np.ndarray, at: float, gain: float) -> None:
    start = int(at * RATE)
    end = min(len(track), start + len(part))
    if end > start:
        track[start:end] += part[: end - start] * gain


def smooth(signal: np.ndarray, cutoff: float) -> np.ndarray:
    """A gentle low-pass by FFT: a second-order roll-off above ``cutoff``, on each channel."""

    n = len(signal)
    size = 1 << (n - 1).bit_length()
    response = 1 / np.sqrt(1 + (np.fft.rfftfreq(size, 1 / RATE) / cutoff) ** 4)
    out = np.empty_like(signal)
    for channel in range(signal.shape[1]):
        out[:, channel] = np.fft.irfft(np.fft.rfft(signal[:, channel], size) * response, size)[:n]
    return out


def reverb(signal: np.ndarray, rng: np.random.Generator, seconds: float = 3.2, wet: float = 0.32) -> np.ndarray:
    """A room made of decaying, decorrelated noise, convolved by FFT."""

    n_ir = int(seconds * RATE)
    decay = np.exp(-np.arange(n_ir) / RATE * 6.9 / seconds)
    ir = smooth(rng.standard_normal((n_ir, 2)) * decay[:, None], 5_000)
    ir[: int(0.012 * RATE)] = 0  # a little pre-delay
    ir /= np.sqrt((ir**2).sum(axis=0))
    size = 1 << (len(signal) + n_ir - 1).bit_length()
    out = np.empty((len(signal), 2))
    for channel in range(2):
        room = np.fft.irfft(np.fft.rfft(signal[:, channel], size) * np.fft.rfft(ir[:, channel], size), size)
        out[:, channel] = signal[:, channel] * (1 - wet) + room[: len(signal)] * wet * 2.2
    return out


def compose(seconds: float) -> np.ndarray:
    rng = np.random.default_rng(7)
    total = int(seconds * RATE)
    pad = np.zeros((total + 4 * RATE, 2))
    bass = np.zeros_like(pad)
    arpeggio = np.zeros_like(pad)
    intro, outro = 2 * CHORD_SECONDS, seconds - CHORD_SECONDS
    chords = [(name, section) for section in plan(seconds) for name in section.chords]
    for index, (name, section) in enumerate(chords):
        at = index * CHORD_SECONDS
        if at >= seconds:
            break
        length = CHORD_SECONDS + 2.2  # each chord rings on into the next
        for note in CHORDS[name]:
            add(pad, pad_note(note, length, rng) * envelope(int(length * RATE), 1.6, 2.4)[:, None], at, 0.16)
        t = np.arange(int(length * RATE)) / RATE
        low = np.sin(2 * np.pi * hz(ROOTS[name]) * t) + 0.2 * np.sin(4 * np.pi * hz(ROOTS[name]) * t)
        add(bass, np.stack([low, low], axis=1) * envelope(len(t), 0.9, 2.0)[:, None], at, 0.20)
        if section.pattern and intro <= at < outro:
            notes, step = [ARPEGGIOS[name][i] for i in section.shape], 0
            for eighth in range(16):
                if section.pattern[eighth % 8]:
                    add(
                        arpeggio,
                        pluck(notes[step % len(notes)], 0.3 if step % 2 else 0.7),
                        at + eighth * BEAT / 2,
                        0.075,
                    )
                    step += 1
    breath = 1 + 0.08 * np.sin(2 * np.pi * 0.07 * np.arange(len(pad)) / RATE)
    mix = smooth(pad * breath[:, None], 2_600) + smooth(bass, 400) + smooth(arpeggio, 6_000)
    mix = reverb(mix, rng)[:total]
    mix *= envelope(total, 2.5, 4.0)[:, None]
    return np.asarray(mix / np.abs(mix).max() * 10 ** (-1 / 20))


def write(path: Path, seconds: float) -> None:
    pcm = (np.clip(compose(seconds), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(pcm.tobytes())


if __name__ == "__main__":
    write(Path(sys.argv[2]), float(sys.argv[1]))
