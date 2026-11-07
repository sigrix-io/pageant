"""What the voice says for a line: its words, with the ones a lesson respells for the voice.

A text-to-speech voice reads some words as they are spelled and not as they are said: a domain's
``.io`` as one syllable, a product's name with the stress where its makers do not put it. A lesson
names those words once (``Lesson.pronounce``), and each is replaced, wherever it stands as a word of
its own, in every line before the voice speaks it. The caption keeps the written form, and a line's
own ``spoken`` words are respelled the same way, so a fix is made once for a whole lesson.

Standard library only, so a lesson's lines can be checked without the voice installed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping


def spoken(words: str, pronounce: Mapping[str, str]) -> str:
    """``words`` as the voice should say them: each key of ``pronounce`` that stands alone, replaced by its value.

    A key matches only where no letter, digit or underscore runs on against either end of it, so
    ``"Sigrix"`` is respelled in ``"Sigrix's"`` and left alone in ``"Sigrixes"``, and the text is read
    once, longest key first, so a domain is respelled before a name inside it and no replacement is
    read again. Keys match as written, capitals included.
    """

    if not pronounce:
        return words
    if any(not key.strip() for key in pronounce):
        raise ValueError("A word to pronounce differently cannot be blank.")
    keys = sorted(pronounce, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(key) for key in keys) + r")(?!\w)")
    return pattern.sub(lambda match: pronounce[match.group(0)], words)


__all__ = ["spoken"]
