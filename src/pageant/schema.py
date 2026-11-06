"""The lesson format's two JSON Schemas, and the small checker that holds a page or a path to them.

A learning site imports a lesson from its bundle, and the format it reads is written down twice:
in ``SPEC.md``, for a person, and in a JSON Schema for each of its two documents, which ship
here: ``lesson.json`` (``sigrix-lesson/1``) and ``path.json`` (``sigrix-learning-path/1``),
under ``schemas/<major version>/``. Beside each is its case table: documents a reader takes, and
documents it refuses, each with the reason. The writer (``bundle.py``) holds every page and path it
writes to its schema, so a lesson whose page the import would refuse is refused here instead,
before anything is recorded or packed.

The checker is the standard library's work, as the rest of the core is, and reads only the
keywords these schemas use: a schema that grows another keyword fails here rather than going
unchecked. Two things in it are narrower than JSON Schema says, both on purpose: an integer is
written as one (``5``, never ``5.0``, which the import refuses), and a pattern is Python's
regular expression, so a pattern that must mean the same in every engine is written in the part
they share (the schemas' ``$comment`` says how a whole value is held). The tests hold the checker,
the schemas and the case tables to a reference implementation of JSON Schema.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

#: The format's major version, which names the folder its schemas are in, and their address.
VERSION = "1"
LESSON = "lesson"
PATH = "path"

#: Read by a person, never checked.
_ANNOTATIONS = frozenset({"$schema", "$id", "$comment", "title", "description"})
_ASSERTIONS = frozenset(
    {
        "type",
        "const",
        "enum",
        "required",
        "properties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "pattern",
        "maxLength",
        "minimum",
        "maximum",
    }
)
#: Every keyword the checker reads; anything else in a schema is refused.
KEYWORDS = _ANNOTATIONS | _ASSERTIONS

_KINDS = {
    "object": "an object",
    "array": "a list",
    "string": "text",
    "integer": "a whole number",
    "number": "a number",
    "boolean": "true or false",
    "null": "null",
}


@dataclass(frozen=True)
class Problem:
    """One rule a document breaks: where it is, which keyword of the schema refuses it, and why, in words.

    ``at`` is a JSON Pointer to the member the rule is about: for a member a document must have, the
    member it lacks; for an item of a list, the item; for the document itself, ``""``.
    """

    at: str
    keyword: str
    message: str

    def __str__(self) -> str:
        return f"{self.at or 'the document'}: {self.message}"


def load(name: str) -> dict[str, Any]:
    """The schema of ``lesson.json`` (``"lesson"``) or of ``path.json`` (``"path"``), as Pageant ships it."""

    return _read(f"{name}.schema.json")


def cases(name: str) -> dict[str, Any]:
    """The case table beside a schema: documents it takes and documents it refuses, each with its reason."""

    return _read(f"{name}.cases.json")


def _read(file: str) -> dict[str, Any]:
    text = resources.files("pageant").joinpath("schemas", VERSION, file).read_text(encoding="utf-8")
    value: dict[str, Any] = json.loads(text)
    return value


def problems(document: Any, schema: Mapping[str, Any]) -> list[Problem]:
    """Every rule of ``schema`` that ``document`` breaks: a value's own rules, then its members' and its items'."""

    found: list[Problem] = []
    _check(document, schema, "", found, "")
    return found


def _check(value: Any, schema: Mapping[str, Any], at: str, found: list[Problem], said: str) -> None:
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise ValueError(f"The schema at {at or 'its root'} uses {sorted(unknown)}, which this checker does not read.")
    # What the rule is for, in words: its own description, or the nearest one around it.
    said = str(schema.get("description", said))
    kind = schema.get("type")
    if kind is not None and not _is(value, kind):
        found.append(Problem(at, "type", f"must be {_KINDS[kind]}, not {_shown(value)}."))
    if "const" in schema and not _same(value, schema["const"]):
        found.append(Problem(at, "const", f"must be {json.dumps(schema['const'])}, not {_shown(value)}."))
    if "enum" in schema and not any(_same(value, option) for option in schema["enum"]):
        options = ", ".join(json.dumps(option) for option in schema["enum"])
        found.append(Problem(at, "enum", f"must be one of {options}, not {_shown(value)}."))
    if isinstance(value, str):
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            found.append(Problem(at, "pattern", f"{_shown(value)} is not of its form. {said}".strip()))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            found.append(Problem(at, "maxLength", f"is {len(value):,} characters, past {schema['maxLength']:,}."))
    if _is(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(Problem(at, "minimum", f"is {value}, below {schema['minimum']}."))
        if "maximum" in schema and value > schema["maximum"]:
            found.append(Problem(at, "maximum", f"is {value}, past {schema['maximum']}."))
    if isinstance(value, dict):
        for member in schema.get("required", ()):
            if member not in value:
                found.append(Problem(f"{at}/{_token(member)}", "required", f"is missing. {_said(schema, member)}"))
        for member, rule in schema.get("properties", {}).items():
            if member in value:
                _check(value[member], rule, f"{at}/{_token(member)}", found, "")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            found.append(Problem(at, "minItems", f"lists {len(value)}, fewer than {schema['minItems']}."))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            found.append(Problem(at, "maxItems", f"lists {len(value)}, more than {schema['maxItems']}."))
        if schema.get("uniqueItems"):
            twice = [item for index, item in enumerate(value) if any(_same(item, seen) for seen in value[:index])]
            if twice:
                found.append(Problem(at, "uniqueItems", f"lists {_shown(twice[0])} more than once."))
        if "items" in schema:
            for index, item in enumerate(value):
                _check(item, schema["items"], f"{at}/{index}", found, said)


def _is(value: Any, kind: str) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    if isinstance(value, bool):
        return False
    if kind == "integer":
        return isinstance(value, int)
    if kind == "number":
        return isinstance(value, int | float)
    raise ValueError(f"The schema names a type, {kind!r}, that JSON does not have.")


def _same(one: Any, other: Any) -> bool:
    """Equal as JSON values are: ``1`` is ``1.0``, and ``true`` is not ``1``, since a boolean is no number."""

    if isinstance(one, list) and isinstance(other, list):
        return len(one) == len(other) and all(_same(a, b) for a, b in zip(one, other, strict=True))
    if isinstance(one, dict) and isinstance(other, dict):
        return one.keys() == other.keys() and all(_same(one[key], other[key]) for key in one)
    if one != other:
        return False
    return type(one) is type(other) or (_is(one, "number") and _is(other, "number"))


def _token(member: str) -> str:
    """A member's name as a JSON Pointer writes it."""

    return member.replace("~", "~0").replace("/", "~1")


def _said(schema: Mapping[str, Any], member: str) -> str:
    rule = schema.get("properties", {}).get(member, {})
    return str(rule.get("description", "")).strip()


def _shown(value: Any) -> str:
    shown = json.dumps(value, ensure_ascii=False)
    return shown if len(shown) <= 60 else shown[:57] + "..."


__all__ = ["KEYWORDS", "LESSON", "PATH", "VERSION", "Problem", "cases", "load", "problems"]
