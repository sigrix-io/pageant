"""The words a lesson respells for the voice (``pageant.pronounce``): replaced where they stand alone, once.

A voice reads some words as spelled: a domain's ``.io`` as one syllable ("dot ee-oh"), which a
published lesson said aloud before a respelling fixed it. The respelling is made once, for the
whole lesson, and these are the edges it keeps.
"""

from __future__ import annotations

import pytest

from pageant.pronounce import spoken

DOMAIN = {"example.io": "example dot eye oh"}


def test_a_word_the_lesson_respells_is_said_its_way_and_the_rest_is_left_alone() -> None:
    assert spoken("On example.io, you pay once.", DOMAIN) == "On example dot eye oh, you pay once."
    assert spoken("Nothing to respell here.", DOMAIN) == "Nothing to respell here."


def test_no_respellings_leave_the_words_as_they_are() -> None:
    assert spoken("On example.io, you pay once.", {}) == "On example.io, you pay once."


def test_a_word_is_respelled_only_where_it_stands_alone() -> None:
    name = {"Acme": "Ack me"}

    assert spoken("Acme's page", name) == "Ack me's page"
    assert spoken("Acmes and acme", name) == "Acmes and acme", "inside a longer word, or in other capitals"
    assert spoken("MyAcme and Acme", name) == "MyAcme and Ack me", "a word that ends in it"
    assert spoken("(Acme)", name) == "(Ack me)"


def test_the_longest_word_is_respelled_first_and_no_respelling_is_read_again() -> None:
    respell = {"example": "ex ample", "example.io": "example dot eye oh"}

    assert spoken("example.io and example", respell) == "example dot eye oh and ex ample"


def test_a_blank_word_is_refused() -> None:
    with pytest.raises(ValueError, match="blank"):
        spoken("anything", {" ": "x"})
