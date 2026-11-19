# Content type for content items

**Status:** Planned. Implementation branch: `feat/content-type`.

Add a `content_type` field to content items (`substrate_article`) so Backfield can tell
different kinds of content apart, and so users can filter and label by kind. The first new kind is
`show_segment`: one segment of a broadcast or podcast show, starting with LAist's AirTalk
daily schedules. Every existing item becomes `article`.

## Why a new field

`external_source` already means the **outlet** (publication name, or URL host as a fallback;
see [`docs/api/public.md`](../api/public.md)). It is also part of each item's identity
(`project_id`, `external_source`, `external_id`). It can't also carry the kind of content:
AirTalk and LAist news are both LAist, and one outlet can publish several kinds.

The two fields answer different questions:

| Item | `external_source` (outlet or show) | `content_type` (kind) |
|------|-------------------------------------|-----------------------|
| LAist news story | `LAist` | `article` |
| AirTalk segment | `AirTalk` | `show_segment` |
| A future podcast segment | the podcast's name | `show_segment` |

The motivating use case is LAist news stories and AirTalk show segments sharing **one
Stylebook**, each in its own project:

```text
Organization: LAist
└── Workspace → Stylebook (shared canonical people, organizations, places)
    ├── Project: LAist stories    flow: news extraction      content_type = article
    └── Project: AirTalk          flow: schedule extraction  content_type = show_segment
```

News and radio share canonical people and organizations. Stylebook already reads a person's
mentions across all projects that point to it. Projects keep API keys, flows, review queues
and model settings separate, so the laist.com key never sees segments. `content_type` labels
each result's kind wherever the two meet: in Stylebook, on the combined search page, and in
future projects that mix kinds.

## Decisions

| Decision | Choice |
|----------|--------|
| Field | `substrate_article.content_type`, `Text`, `NOT NULL`, server default `'article'` |
| Allowed values | Fixed list in code (`StrEnum`): `article`, `show_segment`. New kinds are added in code alongside the flow that produces them |
| Existing rows | Become `article` through the server default; no data rewrite |
| Who sets it | A **Content type** setting on the Backfield Output node, default Article. One flow writes one kind |
| On reprocessing | The flow's value overwrites the stored value. It does not count as a content change, so it does not trigger re-embedding |
| Filtering | Added to the shared article filter (`_apply_public_article_list_filters`). Mention and entity routes already join through the article there, so no mention table gets a copy |
| Index | `idx_substrate_article_project_content_type` on (`project_id`, `content_type`), matching existing per-project article indexes |
| Public API | Optional, repeatable `content_type` filter wherever `external_source` is accepted (e.g. `content_type=article&content_type=show_segment`); the field appears in article responses and in facets |
| Default when the filter is omitted | All kinds, as today. Projects, not a default filter, keep news and show content apart. An articles-only default would hide every segment in a show project's own API |
| Unknown filter value | Rejected with 422 (enum validation), not silently returned empty |
| Table name | `substrate_article` stays as is; renaming is out of scope |

Rejected alternatives:

- **Reuse `external_source`.** It conflicts with the outlet meaning and with item identity.
- **Read `content_type` from each input payload**, like `publication`. That's more flexible,
  but the field becomes invisible in the flow builder and is easy to misspell per item. It
  can be added later if one flow ever needs mixed kinds.
- **Copy the value onto mention tables.** Not needed, because mention filters already join
  the article.
- **One shared project for news and show content, with an articles-only default.** This
  gives one API key and one search across both kinds. But segments could outnumber articles
  (AirTalk alone is roughly 40,000–50,000 segments since 2000). Every public route would
  also depend on a default filter to keep segments out of products like related-story
  widgets. Separate projects give the same sharing through the Stylebook, with cleaner
  access control.
- **A special `all` value.** A repeatable parameter says the same thing without a value that
  isn't a real content type.

## Implementation phases

### 1. Schema and model

- `packages/backfield-db`: add a `ContentType` `StrEnum` and the `content_type` column on
  `SubstrateArticle`.
- Migration `085_article_content_type`: add the column with server default `'article'` and
  create the index. Follow the `082_article_published` pattern. On Postgres, adding a column
  with a constant default doesn't rewrite the table.
- Downgrade drops the index, then the column.

### 2. Ingest

- Backfield Output node (`packages/backfield-agate/src/agate_nodes/db_output`): add
  `content_type` to `defaultParams` (default `"article"`). Add a **Content type** dropdown to
  the panel with the labels Article and Show segment. Follow the frontend copy rules in
  [`docs/development/frontend/conventions.md`](../development/frontend/conventions.md).
- Worker (`apps/worker/src/worker/substrate/content/article.py`): validate the node's value
  against `ContentType`, set it on create, and overwrite it on update. A changed
  `content_type` alone must not mark `content_changed`.
- Update [`docs/development/nodes.md`](../development/nodes.md) if it lists the Backfield
  Output settings.

### 3. Public API

- `packages/backfield-entities/src/backfield_entities/public`:
  - add `content_type` (a tuple of `ContentType`) to the article and mention filter params
    and to the shared article filter. An empty tuple means no filter. Otherwise the shared
    filter applies `content_type IN (…)`
  - semantic and passage search (`article_semantic_search.py`) use the same filter, so the
    filter reaches them without extra code. Add tests to confirm it
  - add `content_types` to `article_facets.py`
  - include `content_type` in the article response builder
- `apps/core-api/src/core_api/routers/public`: add the optional, repeatable `content_type`
  query parameter (`list[ContentType]`), next to each existing `external_source` parameter:
  - article search and the geo-cell batch body
  - mention search
  - the article and mention lists for people, organizations and locations
- Add `content_type` to the article response schema (`articles/responses.py`).
- Regenerate `docs/api/public.openapi.json` with `scripts/export_public_openapi.py`.
- Update [`docs/api/public.md`](../api/public.md): define `content_type`, its values, and how
  it differs from `external_source`.

### 4. API Playground

AGENTS.md requires this for any `/public/v1` change; regenerating OpenAPI isn't enough.

- `apps/api-playground/src/lib/api.ts`, `lib/presentation.ts` and
  `components/EndpointExplorer.tsx`: add a `content_type` control wherever the
  `external_source` control appears. Show it as a multi-select of the two values, not free
  text, with help text saying that leaving it empty returns every kind.
- Update the matching Playground tests.

## Validation

- `make lint` and `make test`.
- Unit tests:
  - enum validation, including a 422 for unknown values
  - the default on create
  - overwrite on update, without `content_changed`
  - the shared filter, applied through article, mention and entity routes
  - the filter in semantic and passage search
  - an omitted filter returning every kind, and repeated values returning both kinds
  - facets returning both values
- Migration: run `make migrate` on a local database with existing articles. Confirm every row
  reads `article`, the index exists, and the downgrade runs cleanly.
- `make smoke`: the golden path still persists articles as `article`.
- Manual check: a flow with Content type set to Show segment writes `show_segment`.
  `content_type=show_segment` returns only that item, and a request without the filter
  returns both kinds.
- Frontend build and tests for `agate-ui` (node panel sync) and `api-playground`.

## Risks

| Risk | Mitigation |
|------|------------|
| Index creation locks `substrate_article` on large production tables | Same exposure as `082_article_published`; run during a quiet window. Switch to `CREATE INDEX CONCURRENTLY` outside the migration transaction if a deployment's table size calls for it |
| Existing API clients see a new response field | The change only adds things: an optional filter and a new field. No existing parameter changes meaning |
| A flow is left on the default and labels segments as articles | The panel shows the setting. The first `show_segment` flow's checklist (below) verifies it |
| `content_type` and `external_source` get confused | Document the difference in `public.md` and in the Playground's help text |

## Notes for the first `show_segment` flow (AirTalk)

These belong to the AirTalk schedule work, not to this change, but they depend on it:

- Create the AirTalk project in the same workspace, pointing to the same Stylebook as the
  LAist stories project.
- Store contact details in a new Stylebook-level table keyed to the canonical person, e.g.
  `stylebook_person_contact`. Existing person metadata is per project, and contacts must be
  shared newsroom-wide. Each value carries:
  - a type (cell, landline, publicist)
  - its source (segment or submitting producer)
  - a date

  Show the newest first, and let producer corrections win. Index the lookup by canonical
  person.
- Set **Content type** to Show segment on the flow's Backfield Output node.
- Put `publication: "AirTalk"` in the payload. Otherwise the outlet falls back to the URL
  host, which for Drive links is `drive.google.com`.
- Use one content item per segment, with `external_id` set to the Drive file ID plus the
  segment letter. Reprocessing then updates segments instead of duplicating them.
- Give each segment a distinct `url`. URLs are unique per project
  (`uq_substrate_article_project_url`), and every segment in a file shares the file's Drive
  link. Append the segment, e.g. `…/view#segment-B`. Drive ignores the fragment, so the link
  still opens the file.
- Store a cleaned version as the segment's `text`: the segment title, topic description,
  guest names and titles, and "can talk about" notes. Leave out:
  - phone numbers and email addresses
  - Zoom links, meeting IDs and passcodes
  - promo and underwriting lines
  - production cues ("ENCO #", "BUMPER IN")
  - pronunciations and link lists

  Two reasons. First, the indexer embeds the headline plus `text`, and that logistics noise
  dilutes segment vectors, so articles would outrank better-matching segments in mixed
  results. Second, `text` is searchable and returned by the public API, so phone numbers
  there would leak outside the contact-info feature. Contacts and pronunciations go into
  structured records instead.
- On the search page, show results grouped by kind ("LAist stories", "AirTalk segments"):
  one query, run against each project. Raw similarity scores aren't calibrated across
  different text styles, so a single ranked list would be biased. Label each result's kind.
  A segment records a booked conversation, and its pre-interview notes are unverified.

## Out of scope

- Renaming `substrate_article` or the public `articles` routes.
- Showing or filtering by content type in the Agate and Stylebook review screens. Add this
  when the producer search page is built.
- Content types beyond `article` and `show_segment`.
