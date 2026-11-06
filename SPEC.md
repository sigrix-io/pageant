# The lesson bundle format

A recorded lesson reaches a learning site as a **bundle**: a folder holding its page and its media
under fixed names. A **pack** is a zip of bundles with the learning path that lists them. Sigrix's
Learn console imports a pack in one step: it checks every lesson, shows what importing it will do,
and saves it. `pageant record` writes a bundle and `pageant pack` writes a pack.

The format has two documents, each with its own name and major version, which every copy of it
says in its `format` member:

- `lesson.json`, a lesson's page: **`sigrix-lesson/1`**;
- `path.json`, a pack's learning path: **`sigrix-learning-path/1`**.

Each has a JSON Schema and a case table, in [`src/pageant/schemas/1/`](src/pageant/schemas/1/).
This page says the same in words, and what no schema can say.

## A bundle

A folder, found by the `lesson.json` in it:

| File | | What it is |
| --- | --- | --- |
| `lesson.json` | required | The lesson's page: below. |
| `video.mp4` | required | The lesson's video: H.264, with its sound in AAC, in an MP4 whose header (`moov`) comes before its media, so a browser can start playing it before it has all of it (ffmpeg's `-movflags +faststart`). |
| `captions.vtt` | optional | The captions, in WebVTT, as UTF-8. |
| `chapters.vtt` | optional | The chapters, in WebVTT: a cue a chapter, its text the chapter's title. |
| `cover.jpg` | optional | The video's poster and the page's cover. It may be `cover.jpeg`, `cover.png` or `cover.webp` instead, but a bundle has one cover at most. |

A reader passes over any other file in the folder, such as `chapters.txt`, which `pageant record`
writes beside the bundle for a YouTube description, or what a Mac adds to a zip.

### `lesson.json`

A JSON object, in UTF-8.

| Member | Required | What it is |
| --- | --- | --- |
| `format` | yes | `"sigrix-lesson/1"`. |
| `slug` | yes | The lesson's address on the site, `/learn/<slug>`: lowercase letters and digits in words joined by single hyphens, such as `notebook-lesson-1-your-first-note`, at most 120 characters. An import updates the lesson already at that address, if there is one, and adds it otherwise. |
| `title` | yes | The page's title: not blank, at most 200 characters. |
| `summary` | yes | A sentence or two under the title, and the page's description for search: not blank, at most 600 characters. |
| `category` | yes | The section of the site the page is filed under: one of `foundations`, `tutorials`, `patterns`, `seller`, `buyer` and `case`. |
| `tags` | no | The tags the site lists the page under, at `/learn/tag/<tag>`: a list of at most 8, each once, each lowercase letters and digits in words joined by single hyphens, at most 32 characters. |
| `body_markdown` | no | The page's text under its video, in Markdown, at most 16,384 characters: half the 32,768 UTF-16 code units Sigrix keeps of a page's text, so that a text this long fits whatever its characters are (an emoji is two code units). |
| `read_minutes` | no | How long the page takes, in whole minutes from 1 to 180, written as a whole number (`5`, not `5.0`). Without it, the site takes the video's length to the nearest minute. |
| `youtube_url` | no | The same video on YouTube, which the page links to and never embeds: `https://www.youtube.com/watch?v=<id>` or `https://youtu.be/<id>`. Left out until the video is there, so an import keeps a link the page already has. |

## A pack

A zip of one or more bundles, at any depth: a zip of one bundle's files, a zip of its folder and a
zip of a folder of folders all read the same. Beside the bundles it may carry one `path.json`,
the learning path that lists them on the site. A slug is the slug of one bundle in a pack: a reader
refuses the second bundle that has it.

### `path.json`

A JSON object, in UTF-8.

| Member | Required | What it is |
| --- | --- | --- |
| `format` | yes | `"sigrix-learning-path/1"`. |
| `title` | yes | The path's title: not blank, at most 120 characters. An import updates the path of the same title, if there is one. |
| `audience` | no | Who the path is for, in a few words: at most 60 characters. |
| `description` | no | What the path covers, in a sentence or two: at most 280 characters. |
| `lessons` | yes | Each lesson's slug, once, in the order the lessons are taken: from 1 to 12 of them, each at most 120 characters. Each is a lesson in the pack or one already on the site. |

## What a reader does

- It refuses a document whose `format` it does not know, and reads a member it does not know as if
  it were not there, so a writer that adds one does not stop an older reader.
- It holds each document to its schema, and the case tables say what that means at every edge:
  each document a reader takes, and each it refuses with the reason (the member, and the rule).
- It holds each file of a bundle to what the site's upload takes for that kind of file, and says
  which file and why when it refuses one.
- It refuses one lesson of a pack without refusing the others, and a path that lists a lesson
  that will be neither in the pack nor on the site.

## The schemas and their case tables

| Document | Schema | Case table |
| --- | --- | --- |
| `lesson.json` | [`lesson.schema.json`](src/pageant/schemas/1/lesson.schema.json), at `https://sigrix.io/schemas/pageant/1/lesson.schema.json` | [`lesson.cases.json`](src/pageant/schemas/1/lesson.cases.json) |
| `path.json` | [`path.schema.json`](src/pageant/schemas/1/path.schema.json), at `https://sigrix.io/schemas/pageant/1/path.schema.json` | [`path.cases.json`](src/pageant/schemas/1/path.cases.json) |

The schemas are JSON Schema 2020-12. Each is published at the address its `$id` names, which ends
in its format's major version. A case table holds `valid`, the documents a reader takes, and
`invalid`, the documents it refuses. Each refused case is made by one RFC 6902 change (a JSON
Patch operation) to a document it takes, so that it is refused for that change and nothing else,
and it gives the reason. The reason is a JSON Pointer to
the member the rule is about, and the schema keyword that refuses it. For a member a document must
have, that is the member it lacks; for an item of a list, the item. A case whose `times` is a
number repeats its change's value that many times, for a text too long to write out. Every
implementation runs both tables: a writer holds what it writes to them, and a reader with a
checker of its own holds that checker to them, so that the two cannot disagree about what the
format allows.

## Versions

A change a reader of `/1` can pass over, such as a new member, keeps the version. A change a
reader of `/1` would misread or refuse is a new major version, `sigrix-lesson/2`. Its schema is
published at a new address, `https://sigrix.io/schemas/pageant/2/`, beside the old one. A published
address is never withdrawn and never reused for anything else. Pageant writes the versions the
import reads, and moves to a new one only once the import reads it.
