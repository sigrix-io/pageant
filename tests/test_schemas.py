"""The lesson format's two JSON Schemas, their case tables, and the writer held to them (``pageant.schema``).

A bundle's ``lesson.json`` and a pack's ``path.json`` are a format two programs share: Pageant
writes it, and a learning site's import reads it. Each document has a JSON Schema and a case
table beside it, and a mirrored rule fails silently, so here:

1. **Each table holds under the checker Pageant writes with, and under a reference
   implementation of JSON Schema**: every document it takes passes, and every document it
   refuses is refused for one reason, the one the table gives (where, and by which keyword).
2. **Every rule a schema states has a case that is refused for it**, so a rule cannot join a
   schema without the table saying how it is broken, and a slug is one pattern wherever it is.
3. **The writer writes only documents the schemas take**: every refused case a page or a path
   can express is refused by the writer with the table's reason, and ``pageant record`` and
   ``pageant pack`` stop on one before anything is filmed or zipped.
4. **The schemas name their own addresses** and the formats the writer writes, and ``SPEC.md``
   states every member and limit they do.
"""

from __future__ import annotations

import copy
import dataclasses
import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from pageant import bundle, schema

ROOT = Path(__file__).resolve().parents[1]
NAMES = (schema.LESSON, schema.PATH)
SCHEMAS = {name: schema.load(name) for name in NAMES}
TABLES = {name: schema.cases(name) for name in NAMES}
FORMATS = {schema.LESSON: bundle.LESSON_FORMAT, schema.PATH: bundle.PATH_FORMAT}


def _apply(document: Any, case: dict[str, Any]) -> Any:
    """One RFC 6902 add, replace or remove applied to a copy, strictly: an add may not overwrite a member,
    and a replace or a remove must find one, so a misspelt path cannot pass as a refusal. A case's
    ``times`` repeats a text value that many times."""

    change = case["change"]
    value = change.get("value")
    if "times" in case:
        assert isinstance(value, str), case["name"]
        value = value * case["times"]
    if change["path"] == "":
        assert change["op"] == "replace", case["name"]
        return copy.deepcopy(value)
    changed = copy.deepcopy(document)
    tokens = [token.replace("~1", "/").replace("~0", "~") for token in change["path"][1:].split("/")]
    *parents, last = tokens
    target = changed
    for token in parents:
        target = target[int(token)] if isinstance(target, list) else target[token]
    if isinstance(target, list):
        index = int(last)
        assert change["op"] == "add" or index < len(target), case["name"]
        if change["op"] == "add":
            target.insert(index, value)
        elif change["op"] == "replace":
            target[index] = value
        else:
            del target[index]
        return changed
    if change["op"] == "add":
        assert last not in target, f"add would overwrite {change['path']} in {case['name']!r}"
        target[last] = value
    elif change["op"] == "replace":
        assert last in target, f"nothing to replace at {change['path']} in {case['name']!r}"
        target[last] = value
    else:
        assert last in target, f"nothing to remove at {change['path']} in {case['name']!r}"
        del target[last]
    return changed


def _documents(name: str) -> dict[str, Any]:
    """Each document the table takes, by its case's name: written out, or made from one written out."""

    made: dict[str, Any] = {}
    for case in TABLES[name]["valid"]:
        assert case["name"] not in made, f"two cases named {case['name']!r}"
        made[case["name"]] = case["document"] if "document" in case else _apply(made[case["base"]], case)
    return made


DOCUMENTS = {name: _documents(name) for name in NAMES}
VALID = [(name, case_name) for name in NAMES for case_name in DOCUMENTS[name]]
INVALID = [(name, case) for name in NAMES for case in TABLES[name]["invalid"]]


def _refused(name: str, case: dict[str, Any]) -> Any:
    return _apply(DOCUMENTS[name][case["base"]], case)


def _reference_reasons(document: Any, name: str) -> list[dict[str, str]]:
    """Why the reference implementation refuses ``document``: each error's member and keyword, as the table says them."""

    validator = jsonschema.Draft202012Validator(SCHEMAS[name])
    reasons = []
    for error in validator.iter_errors(document):
        at = "".join(f"/{part}" for part in error.absolute_path)
        if error.validator == "required":
            [missing] = [member for member in error.validator_value if member not in error.instance]
            at += f"/{missing}"
        reasons.append({"at": at, "keyword": str(error.validator)})
    return reasons


# --------------------------------------------------------------------------- #
# 1. The tables, under the checker and under a reference implementation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", NAMES)
def test_each_schema_is_one_json_schema_reads(name: str) -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMAS[name])
    assert SCHEMAS[name]["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize(("name", "case_name"), VALID, ids=[f"{n}: {c}" for n, c in VALID])
def test_a_document_the_table_takes_passes_the_checker_and_the_reference(name: str, case_name: str) -> None:
    document = DOCUMENTS[name][case_name]

    assert schema.problems(document, SCHEMAS[name]) == []
    assert _reference_reasons(document, name) == []


@pytest.mark.parametrize(("name", "case"), INVALID, ids=[f"{n}: {c['name']}" for n, c in INVALID])
def test_a_document_the_table_refuses_is_refused_for_its_reason_alone(name: str, case: dict[str, Any]) -> None:
    document = _refused(name, case)

    found = schema.problems(document, SCHEMAS[name])
    assert [{"at": problem.at, "keyword": problem.keyword} for problem in found] == [case["reason"]]
    assert _reference_reasons(document, name) == [case["reason"]], "the reference refuses it for that and nothing else"
    assert str(found[0]).startswith(f"{case['reason']['at'] or 'the document'}: ")


def test_the_checker_reads_every_keyword_the_schemas_use_and_refuses_one_it_does_not() -> None:
    def keywords(node: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(key)
                if key == "properties":
                    for member in value.values():
                        found |= keywords(member)
                elif isinstance(value, dict | list):
                    found |= keywords(value)
        elif isinstance(node, list):
            for item in node:
                found |= keywords(item)
        return found

    used = set().union(*(keywords(document) for document in SCHEMAS.values()))
    assert used - schema.KEYWORDS == set()
    with pytest.raises(ValueError, match=r"\['minLength'\], which this checker does not read"):
        schema.problems("a slug", {"type": "string", "minLength": 3})


@pytest.mark.parametrize(
    ("value", "rule", "keyword"),
    [
        (True, {"type": "integer"}, "type"),
        (5.0, {"type": "integer"}, "type"),
        (True, {"enum": [1]}, "enum"),
        ([1, True], {"uniqueItems": True}, None),
        ([1, 1.0], {"uniqueItems": True}, "uniqueItems"),
        ("ä" * 3, {"maxLength": 3}, None),
    ],
    ids=["true is no integer", "5.0 is written as 5", "true is not 1", "1 and true differ", "1 is 1.0", "characters"],
)
def test_the_checker_reads_values_as_json_does(value: Any, rule: dict[str, Any], keyword: str | None) -> None:
    assert [problem.keyword for problem in schema.problems(value, rule)] == ([keyword] if keyword else [])


# --------------------------------------------------------------------------- #
# 2. Every rule has a case, and a slug is one pattern
# --------------------------------------------------------------------------- #


def _rules(name: str) -> set[tuple[str, str]]:
    """Every (member, keyword) a schema states, an item of a list as ``*``: what a refused case can be refused for."""

    def walk(rule: dict[str, Any], at: str) -> set[tuple[str, str]]:
        found = {
            (at, key)
            for key in rule
            if key in schema.KEYWORDS
            and key not in {"$schema", "$id", "$comment", "title", "description", "properties", "items", "required"}
        }
        found |= {(f"{at}/{member}", "required") for member in rule.get("required", ())}
        for member, inner in rule.get("properties", {}).items():
            found |= walk(inner, f"{at}/{member}")
        if "items" in rule:
            found |= walk(rule["items"], f"{at}/*")
        return found

    return walk(SCHEMAS[name], "")


@pytest.mark.parametrize("name", NAMES)
def test_every_rule_a_schema_states_has_a_case_refused_for_it(name: str) -> None:
    reasons = {
        (re.sub(r"/\d+(?=/|$)", "/*", case["reason"]["at"]), case["reason"]["keyword"])
        for case in TABLES[name]["invalid"]
    }

    assert len(_rules(name)) >= 10, "the walk found the schema's rules"
    assert _rules(name) - reasons == set(), "a rule no case breaks"
    assert reasons - _rules(name) == set()


def test_a_slug_is_one_pattern_wherever_the_format_names_one() -> None:
    lesson = SCHEMAS[schema.LESSON]["properties"]
    slugs = {
        lesson["slug"]["pattern"],
        lesson["tags"]["items"]["pattern"],
        SCHEMAS[schema.PATH]["properties"]["lessons"]["items"]["pattern"],
    }

    assert len(slugs) == 1
    assert SCHEMAS[schema.PATH]["properties"]["lessons"]["items"]["maxLength"] == lesson["slug"]["maxLength"]


# --------------------------------------------------------------------------- #
# 3. The writer writes only what the schemas take
# --------------------------------------------------------------------------- #

#: A page's members, as ``Page`` names them and the types it declares for them.
PAGE_FIELDS = {
    "slug": "slug",
    "title": "title",
    "summary": "summary",
    "category": "category",
    "tags": "tags",
    "body_markdown": "body",
    "youtube_url": "youtube_url",
}
PATH_FIELDS = {"title": "title", "audience": "audience", "description": "description", "lessons": "lessons"}


def _page(document: dict[str, Any]) -> bundle.Page:
    return bundle.Page(
        folder="a-lesson",
        slug=document["slug"],
        title=document["title"],
        summary=document["summary"],
        body=document.get("body_markdown", ""),
        category=document["category"],
        tags=tuple(document.get("tags", ())),
        youtube_url=document.get("youtube_url", ""),
    )


def _path(document: dict[str, Any]) -> bundle.LearningPath:
    least = DOCUMENTS[schema.LESSON]["the least a lesson may say"]
    return bundle.LearningPath(
        title=document["title"],
        audience=document.get("audience", ""),
        description=document.get("description", ""),
        lessons=tuple(_page({**least, "slug": slug}) for slug in document["lessons"]),
    )


def _cannot_write(name: str, case: dict[str, Any]) -> str:
    """Why a writer given a page or a path cannot write this case, or ``""`` if it can."""

    fields = PAGE_FIELDS if name == schema.LESSON else PATH_FIELDS
    member = case["change"]["path"].split("/")[1] if case["change"]["path"] else ""
    if member not in fields:
        return (
            "a member the writer writes for itself, or none"
            if member in {"", "format"}
            else "a member a page has no field for"
        )
    if case["change"]["op"] == "remove":
        return "a member the writer always writes"
    value = _refused(name, case)[member]
    declared = list if member in {"tags", "lessons"} else str
    if not isinstance(value, declared) or (declared is list and not all(isinstance(item, str) for item in value)):
        return "a value of a kind the field's type forbids"
    return ""


WRITABLE = [(name, case) for name, case in INVALID if not _cannot_write(name, case)]


@pytest.mark.parametrize(("name", "case"), WRITABLE, ids=[f"{n}: {c['name']}" for n, c in WRITABLE])
def test_the_writer_refuses_a_page_or_a_path_the_table_refuses_with_its_reason(name: str, case: dict[str, Any]) -> None:
    document = _refused(name, case)

    with pytest.raises(bundle.ManifestRefused) as refused:
        if name == schema.LESSON:
            bundle.page_json(_page(document))
        else:
            bundle.path_json(_path(document))
    [(file, problem)] = refused.value.problems
    assert {"at": problem.at, "keyword": problem.keyword} == case["reason"]
    assert file == ("a-lesson/lesson.json" if name == schema.LESSON else "path.json")


def test_what_the_writer_cannot_be_given_is_only_what_a_page_cannot_say() -> None:
    """The cases left out above are the ones a page or a path cannot carry, and no more: their format, a
    member left out, a read time (a page has none), and a value its field's type forbids."""

    skipped = {(name, case["name"]): _cannot_write(name, case) for name, case in INVALID if _cannot_write(name, case)}

    assert len(WRITABLE) >= 30, "most refusals are ones a page or a path can make"
    assert set(skipped.values()) == {
        "a member the writer writes for itself, or none",
        "a member a page has no field for",
        "a member the writer always writes",
        "a value of a kind the field's type forbids",
    }
    assert {case for (_, case), why in skipped.items() if why == "a member a page has no field for"} == {
        "a read time written as text",
        "a read time with a fraction",
        "a read time of no minutes",
        "a read time past three hours",
    }


@pytest.mark.parametrize(("name", "case_name"), VALID, ids=[f"{n}: {c}" for n, c in VALID])
def test_the_writer_writes_what_the_table_takes_as_the_table_says_it(name: str, case_name: str) -> None:
    """Every document the table takes, as far as a page or a path can say it: a page has no read time,
    and neither says a member the format does not name."""

    document = DOCUMENTS[name][case_name]
    fields = PAGE_FIELDS if name == schema.LESSON else PATH_FIELDS
    sayable = {key: value for key, value in document.items() if key == "format" or key in fields}

    written = bundle.page_json(_page(document)) if name == schema.LESSON else bundle.path_json(_path(document))

    assert {key: value for key, value in written.items() if key in sayable} == sayable
    assert set(written) - set(sayable) <= {"tags", "body_markdown", "audience", "description"}, "only its empty members"


FIRST = bundle.Page(
    folder="first-note",
    slug="notebook-lesson-1-your-first-note",
    title="Notebook lesson 1: your first note",
    summary="Write a note and add it.",
    body="## What you will see\n\n- A note.\n",
    tags=("notebook", "video"),
)


def test_a_pack_with_a_page_or_a_path_the_schemas_refuse_says_every_reason_and_writes_nothing(tmp_path: Path) -> None:
    capitals = dataclasses.replace(FIRST, folder="capitals", slug="Notebook Lesson 1")
    untagged = dataclasses.replace(FIRST, folder="untagged", slug="notebook-lesson-2", tags=("Video",))
    path = bundle.LearningPath(title="Notebook", audience="", description="", lessons=(capitals, untagged, untagged))

    with pytest.raises(bundle.ManifestRefused) as refused:
        bundle.pack(tmp_path, path, tmp_path / "lessons.zip")

    assert [(file, problem.at, problem.keyword) for file, problem in refused.value.problems] == [
        ("capitals/lesson.json", "/slug", "pattern"),
        ("untagged/lesson.json", "/tags/0", "pattern"),
        ("untagged/lesson.json", "/tags/0", "pattern"),
        ("path.json", "/lessons", "uniqueItems"),
        ("path.json", "/lessons/0", "pattern"),
    ]
    said = str(refused.value)
    assert said.startswith(
        "A learning site's import would refuse what these would write:\n- capitals/lesson.json, /slug: "
    )
    assert '"Notebook Lesson 1" is not of its form.' in said
    assert list(tmp_path.iterdir()) == [], "nothing is written"


# --------------------------------------------------------------------------- #
# 4. Addresses, formats, and the spec
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", NAMES)
def test_a_schema_names_its_address_its_table_names_it_and_it_names_the_writers_format(name: str) -> None:
    address = f"https://sigrix.io/schemas/pageant/{schema.VERSION}/{name}.schema.json"

    assert SCHEMAS[name]["$id"] == TABLES[name]["schema"] == address
    assert SCHEMAS[name]["properties"]["format"]["const"] == FORMATS[name]
    assert FORMATS[name].endswith(f"/{schema.VERSION}"), "the address carries the format's major version"


def test_every_schema_and_table_ships_and_nothing_else_is_there() -> None:
    shipped = sorted(path.name for path in (ROOT / "src" / "pageant" / "schemas" / schema.VERSION).iterdir())

    assert shipped == sorted(f"{name}.{kind}.json" for name in NAMES for kind in ("schema", "cases"))


@pytest.mark.parametrize("name", NAMES)
def test_the_spec_states_every_member_and_every_limit_of_each_schema(name: str) -> None:
    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    heading = {schema.LESSON: "### `lesson.json`", schema.PATH: "### `path.json`"}[name]
    section = re.split(r"\n#{2,3} ", spec.split(heading, 1)[1], maxsplit=1)[0]
    rows = {match.group(1): match.group(0) for match in re.finditer(r"^\| `(\w+)` \|.*$", section, re.MULTILINE)}
    members = SCHEMAS[name]["properties"]

    assert list(rows) == list(members), "the spec's table names each member, in the schema's order"
    for member, rule in members.items():
        limits = [rule[key] for key in ("maxLength", "maximum", "maxItems") if key in rule]
        limits += [rule["items"][key] for key in ("maxLength",) if key in rule.get("items", {})]
        for limit in limits:
            assert f"{limit:,}" in rows[member], (member, limit)
        required = member in SCHEMAS[name]["required"]
        assert ("| yes |" in rows[member]) == required, member
