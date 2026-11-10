# Content Temporality Classification Service

## Categories
- evergreen
- anchored
- supersedable
- recurring_instance

Classify how the story at the end of this prompt relates to time, and determine whether it hinges on a moment that expires. Return only valid JSON.

Two independent judgments:

1. **`category`** (the temporal class) — does this story's usefulness decay, and if so, how?
2. **`expires_after`** — is there a specific date after which it stops being current?

A story can be `evergreen` with no expiry, `supersedable` with a hard expiry, or `anchored` with no expiry at all. Decide each on its own.

## The classification test

Work the four questions **in order** and stop at the first that fits. The order matters: several stories satisfy more than one description, and the earlier categories carry the more consequential failure modes.

**1. Does old information become literally *false* when something specific happens?** → `supersedable`

A claim that is true, then categorically false the moment a specific thing occurs — a hard boundary, not gradual decay. Current officeholders. Election-cycle candidates. Whether a policy, moratorium, or program is still active. Current prices, fares, or fees. Deadline status.

This is the dangerous category. A stale answer here is not presented as "somewhat old" — it is presented with the same confidence as a current fact, and a reader cannot detect the problem from the story alone.

**2. Does the same subject *repeat* on a cadence, with new but equally true specifics each cycle?** → `recurring_instance`

Each occurrence is independently and completely true; neither is "wrong." The canonical case: Big Bear eagle nesting seasons — last year's eaglets are a real, separate instance from this year's. Annual festivals, budget cycles, seasonal guides, yearly rankings.

The failure mode here is *conflation*, not staleness: two near-identical instances blended into one incoherent answer.

**3. Is interest driven by *one fixed past event* that does not repeat?** → `anchored`

Tied to a specific historical moment; interest is dormant and spikes on external triggers — anniversaries, related news, a documentary. Old coverage remains fully true. A missed resurfacing opportunity is the only failure, not an error.

**4. None of the above?** → `evergreen`

Usefulness independent of when it is read. Explainers, how-tos, guides, service pieces, background, profiles that are not pegged to a passing moment. **This is the default**, and the category everything else is an exception to.

### Old is not the same as decaying

Age is not the test — *kind* is. A years-old explainer is `evergreen`; a story published yesterday about a vote scheduled for tomorrow is `supersedable`. Do not let the publish date pull the classification.

Do not reach for `supersedable` because a story merely *mentions* a price, an official, or a deadline. Ask whether the story's central claim becomes false. A profile of a council member that mentions their seat is not supersedable; a story reporting who currently holds the seat is.

## `expires_after`

**Default is `null`. An expiry must be earned.**

Set a date only when **all three** hold:

1. The story hinges on a moment — an event, deadline, window, or "this week" framing — such that after it passes, the story is no longer a useful thing to recommend.
2. That moment is **relative to publication**, not to something inside the story's own narrative.
3. You can resolve it to a specific date from the publish date given below.

### The distinction that matters most

Relative dates come in two kinds, and only one is resolvable against the publish date.

**Publication-relative** — the writer means "relative to when you're reading this":
- "The ceremony will air **on Monday**" → the Monday after the publish date
- "Tickets go on sale **this Saturday**" → that Saturday
- "The deadline is **next Friday**" → that Friday

**Narrative-relative** — anchored to an event inside the story, not to publication:
- "Belafonte and the estate settled out of court **the next year**" → the year after *the lawsuit*, not after publication
- "The ceremony was delayed amidst the strikes **last year**" → relative to the events described

Resolving a narrative-relative phrase against the publish date produces a confidently wrong date. **When you cannot tell which kind you are looking at, return `null`.**

### Resolvable is not the same as expiring

A date you can resolve does not by itself create an expiry. "The film took $22.2 million **on Thursday**" resolves cleanly and expires nothing — it is a reported past fact, not a forthcoming moment the story is built around.

Ask: *after this date passes, is this story still worth recommending to a reader?* If yes, `expires_after` is `null`.

### Which direction to err

A wrong expiry silently removes a good story from every future recommendation. A missing expiry merely leaves things as they are. **When in doubt, return `null`.**

## Fields

### category

The temporal class. Exactly one of: `evergreen`, `anchored`, `supersedable`, `recurring_instance`.

### confidence

`high`, `medium`, or `low`. Use `low` honestly — a low-confidence classification is more useful than a falsely certain one.

### rationale

One sentence, under 25 words, specific to *this* story. Name what makes it decay or not decay — not the rule you applied.

- Good: `Reports who currently chairs the board; false as soon as the seat changes.`
- Good: `Explains how the permit process works, with no pegged event.`
- Bad: `This is supersedable content.` (restates the label)

### expires_after

`YYYY-MM-DD`, or `null`. Null unless all three conditions above hold.

### expiry_basis

The **verbatim phrase** from the story that you resolved, or `null` when `expires_after` is null. This is what makes an expiry auditable against the text — a date with no basis cannot be checked.

## Output

Return **only** valid JSON in exactly this shape. No text before or after.

```json
{
  "category": "supersedable",
  "confidence": "high",
  "rationale": "Hinges on the Emmys airing Monday; afterward the how-to-watch framing is spent.",
  "expires_after": "2026-01-16",
  "expiry_basis": "will air on Monday"
}
```

## Publish Date

{publish_date}

## Text to Analyze

{text}
