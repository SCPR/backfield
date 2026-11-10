# Story Temporality: Evergreen, Seasonal, or News

Decide how the story at the end of this prompt relates to time, so a newsroom knows whether it is still worth recommending later. Return only valid JSON.

## Categories
- evergreen
- seasonal
- news

## The question

Judge the story **as of its publish date** (given below), not today.

- **`evergreen`** — about a topic that stays relevant to readers regardless of the news cycle or the season: a how-to, a guide whose advice does not depend on recent events, an explainer of how something works, a history told as history, a recipe, a profile of something that does not change. Reading it a year from now would serve a reader about as well as reading it today.
- **`seasonal`** — tied to a recurring occasion rather than a one-time event: a holiday, a season, a yearly event. Its value returns each time the occasion comes around (Thanksgiving recipes, a holiday gift guide, how to prepare for fire season, a guide to the Rose Parade).
- **`news`** — reports something time-bound: something that had just happened, was happening, or was scheduled when it was published. **Any scale counts**: a council vote, a restaurant opening, a festival this weekend, a new study's findings, a court ruling, a disaster and its aftermath. A story about a new study is news: a newer study can replace it.

**Evergreen needs clear evidence. When in doubt between evergreen and news, choose `news`.** Treating news as evergreen keeps a stale story in front of readers; treating an evergreen story as news only retires it early.

A news peg does not make a story news if the peg is only framing: a guide to basmati rice published as Diwali begins is evergreen (or seasonal) if its substance does not depend on the date.

## For `news`

**`event_kind`** — is the story about a **one-off** event (a game, a verdict, an award ceremony, an election result, an opening day) or part of an **ongoing** situation that keeps developing (a recovery, a trial, a policy fight, an agency's turmoil, a campaign)?

**`stale_after`** — a date after which this story is out of date, **only if** the story hinges on a forthcoming, publication-relative moment you can resolve with confidence ("the ceremony will air Monday", "the board is expected to vote Oct. 21"; take the year from the publish date). Otherwise `null`. Do not resolve a phrase that is relative to an event inside the story ("the next year", "last spring") against the publish date. A date that is a reported past fact ("the film took $22 million on Thursday") is not a `stale_after`. Never guess: `null` is safe.

## For `evergreen` and `seasonal`

**`perishable_details`** — does the story's usefulness depend on specifics that change: businesses, prices, links, availability, event dates, program rules? A gift guide naming stores is `true` (the stores may close even if the gift idea holds); a history of the Watts Towers is `false`.

**`occasion`** (seasonal only) — the recurring occasion, as a short name: "Thanksgiving", "Diwali", "fire season", "back to school".

## Fields

- `category`: `evergreen`, `seasonal`, or `news`.
- `confidence`: `high`, `medium`, or `low`. Use `low` honestly.
- `rationale`: one sentence, under 25 words, specific to this story.
- `evidence`: the shortest verbatim phrase from the story that best supports the category.
- `event_kind`: `one_off` or `ongoing` for news; otherwise `null`.
- `stale_after`: `YYYY-MM-DD` or `null` (news only).
- `stale_after_basis`: the verbatim phrase you resolved, or `null`.
- `perishable_details`: `true` or `false` for evergreen and seasonal; otherwise `null`.
- `occasion`: a short name for seasonal; otherwise `null`.

## Output

Return **only** valid JSON in exactly this shape. No text before or after.

```json
{
  "category": "news",
  "confidence": "high",
  "rationale": "Previews the Emmys broadcast Monday; once winners are announced, the picks and viewing guide are spent.",
  "evidence": "will air on Monday",
  "event_kind": "one_off",
  "stale_after": "2026-09-14",
  "stale_after_basis": "will air on Monday",
  "perishable_details": null,
  "occasion": null
}
```

## Publish Date

{publish_date}

## Text to Analyze

{text}
