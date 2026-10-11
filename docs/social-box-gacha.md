# Social Box Gacha — Setup & Deploy Guide (Plain-English)

This guide explains **Social Box Gacha** ("SBG") in Brick — what it is, how
its two building blocks fit together, how to create/edit one, and how to
push your changes live. It is written for people with **no coding
background** — if you can fill out a web form, you can follow this.

Investigated live against `sgs-brick-live` on 2026-09-10, using real records:
- SBG Event `dxvault_hieunm_test1001_DNU`
- SBG Segment `subsbg_hieunm_test_100926`

## Contents

1. [What Is Social Box Gacha?](#what-is-social-box-gacha)
2. [Where It Lives](#where-it-lives)
3. [The Two Building Blocks](#the-two-building-blocks)
4. [SBG Event — Field by Field](#sbg-event--field-by-field)
5. [SBG Segment — Field by Field](#sbg-segment--field-by-field)
6. [How to Create a New One](#how-to-create-a-new-one)
7. [How to Deploy It](#how-to-deploy-it)
8. [Common Mistakes to Avoid](#common-mistakes-to-avoid)

---

## What Is Social Box Gacha?

"Social Box Gacha" is a lootbox ("gacha box") feature that players open as
part of a **group/social activity** — the box's content, cost, and refresh
rules can change depending on whether the player is playing solo or with a
team. It is made of **two separate records that work together**:

- **SBG Event** — the "what": which box is this, what does it look like,
  what does it say to the player.
- **SBG Segment** — the "how much / how often": the cost to open the box,
  how it refreshes, and rules for group play (team size, prize tiers, etc.).

One Event points at one Segment (through a dropdown field, explained below),
but the same Segment can be reused by several Events.

## Where It Lives

Sidebar → **Live Events** → **Social Box Gacha** → then pick one of:

| Sidebar item | List page URL | What it is |
|---|---|---|
| **SBG Event** | `/wp_sbg/list/` | The box's content & display |
| **SBG Segment** | `/wp_sbg/segment/list/` | The box's cost & refresh rules |

Both list pages look and behave the same way:
- A **Filter Data** search box at the top (search by ID).
- A table where every row has an **Edit** (pencil) and **Clone** icon on
  the far left.
- An **"Add New ..."** button to create a brand-new record from scratch.
- Two columns at the far right, **Deployed to live** / **Deployed to
  liveops**, showing a red ✘ if the record has never been pushed to that
  environment, or a green check once it has.

> By default, test/QA rows (Gate = `LiveopsTest`, see below) are hidden by a
> "Hide LiveopsTest gate items" checkbox on the list page. If you can't find
> a test record you just made, uncheck that box.

## The Two Building Blocks

Both records share two fields that exist on **every** Brick feature, not
just Social Box Gacha:

- **Gate** — a shared dropdown (~2,800 entries) used across the whole game
  to control *when/where* a piece of content is visible. Test/QA-only
  content typically uses the `LiveopsTest` gate; a real live feature uses a
  gate tied to a specific release. If you're not sure which Gate to pick,
  ask your producer/lead — don't leave it on the Clone dialog's default
  (see [Common Mistakes](#common-mistakes-to-avoid)).
- **Variant** — used for A/B testing cohorts. It shows as a column on the
  list (usually `—` if not in an A/B test) and is generally managed by a
  separate deployment step ("Process A/B Variants"), not by hand on these
  forms.

## SBG Event — Field by Field

Open one by clicking the **Edit** (pencil) icon on its row.

| Field on screen | What it means |
|---|---|
| Gate | See above. |
| Event ID | The unique internal name for this box event. Can't be changed once created — pick carefully. |
| Event Type | Who this box mode is for: `Shared`, `Personal` (solo), `Group vs Group`, or `Faction vs Faction`. This decides whether the linked Segment's team/player-count rules apply. |
| Display Name | The **title** players see. This is a localization ("LOC") field — the box shows a placeholder key like `!!SOME_KEY` until real, translated text is set up for it (double-click the field to create/edit the translated text). |
| Description | The **body text** players see (e.g. the tagline under the title). Also a LOC field, same double-click behavior. |
| Loot Texture | The internal art/image path used to render the box (e.g. `UI/Gacha/MegaSS_Gacha_Anniversary`). This must match an actual art asset already in the game — ask an artist/engineer if unsure what to put here. |
| Leanplum Variable | An integration hook name for Leanplum (the marketing/analytics tool), **not** a reference to an SBG Segment despite the similar-sounding name. Leave as-is unless marketing/analytics asks you to change it. |
| SegmentID | **This is the real link to SBG Segment.** A dropdown listing every SBG Segment record that exists — pick the one whose cost/refresh rules should apply to this box. |
| Priority | A number used to decide which box "wins" if more than one could show at once. Higher usually means "shown first" — check with a producer for the convention your team uses. |
| AllowHCSupplement | A checkbox. When on, players are allowed to top up with Hard Currency (paid currency) if they're short on the box's normal currency. |
| Is Locked | A checkbox that locks the record from further edits. Leave off unless you specifically want to freeze it. |

## SBG Segment — Field by Field

Open one by clicking the **Edit** (pencil) icon on its row.

| Field on screen | What it means |
|---|---|
| Gate | Same shared Gate dropdown as above. |
| SegmentID | The unique internal name for this rule-set. This is the value that shows up in the Event's "SegmentID" dropdown. |
| Max Players | How many players can be in a group for this box (`1` = solo-only). |
| Team Count | How many teams are involved (relevant for Group-vs-Group / Faction-vs-Faction event types). |
| Cost Adj Interval | How often (in seconds) the box's cost re-adjusts. A very large number like `999999999` effectively means "never." |
| PT Boost Chance | Starting chance (0.0–1.0) that a "point boost" bonus triggers on a pull. |
| PT Boost Increase | How much that chance grows each time it doesn't trigger (a "pity" style increase). |
| Box Refresh Type | Dropdown: `Minimum Value` or `Sum Value` — how refresh cost is calculated when multiple refresh sources apply. |
| Box Refresh HC | How much Hard Currency it costs to manually refresh the box early. |
| Box Refresh limit | Maximum number of manual refreshes allowed (`0` = unlimited, in most Brick features — confirm with a designer for this exact box). |
| Diff Limit | Caps how far the box's internal "difficulty"/value score can drift before it's clamped back. |
| High Priority | Which prize tier is treated as the "big/rare" prize for this box. |
| Chase Priority | Which prize tier is treated as the secondary "chase" prize. |
| Is Refresh Progress | Checkbox — when on, progress toward the next refresh carries over instead of resetting. |
| **Cost table** (Init / Min / Max Cost, and Coeff) | A small 2-column table appears near the bottom, one column for **Limited Time Currency (LTC)** and one for **Hard Currency (HC)**: <br>• **Init Cost** — the starting price to open the box.<br>• **Min Cost** / **Max Cost** — the floor/ceiling the price is allowed to move to as it adjusts over time.<br>• **Coeff** — the multiplier applied each time the price adjusts. `1.0` = price never changes on its own. |

## How to Create a New One

You have two options — for both SBG Event and SBG Segment:

**Option A — Add New (start from a blank form)**
1. Go to the list page (SBG Event or SBG Segment).
2. Click **"Add New ..."** in the top-right.
3. Fill in every field described above, then **Save**.

**Option B — Clone (start from an existing one, recommended for most cases)**
1. Find a similar existing record on the list page (use **Filter Data** to
   search by ID).
2. Click its **Clone** icon.
3. A small popup appears with two fields:
   - **New Event ID** / **New Segment ID** — pre-filled as
     `<original-id>_Cloned`. Change this to your own unique ID.
   - **Gate** — ⚠️ this defaults to `delete`, which is **not** a real gate.
     Always change it to the correct Gate for your work (often
     `LiveopsTest` while you're still testing).
4. Click **Clone**. You're now editing the new copy — adjust whatever
   fields need to be different from the original, then **Save**.

Either way, remember: if you're building an **SBG Event**, you also need an
**SBG Segment** to point it at (create/reuse one via the SegmentID
dropdown) — the Event alone won't have cost/refresh rules without it.

## How to Deploy It

Creating and saving a record only stores it in the tool — it does **not**
put it in front of players. To actually ship it, you "process" it through
the deployment page:

1. Click **The Brick logo** (top-left) to go to the Home page — this is the
   **Process Blueprints** screen.
2. In the long checklist of feature checkboxes, find and check
   **"Social Box Gacha"**. (If you changed *only* SBG Event/Segment data,
   you only need this one box checked — no need to select unrelated
   features.)
3. Choose the target **Environment** from the dropdown:
   - `Development` / `Staging` — internal/QA environments, safe to test in.
   - `LiveOps` / `Live` — real, player-facing environments.
4. Click **Process**.
5. Go back to the SBG Event/Segment list page and confirm the **"Deployed
   to live"** / **"Deployed to liveops"** column now shows a green check
   for your record.

> Tip: always process to a test environment first (`LiveopsTest` gate +
> `Development`/`Staging` environment) and verify in-game before deploying
> the same content to `Live`.

## Common Mistakes to Avoid

- **Leaving Clone's Gate on `delete`.** The Clone popup pre-selects the
  first alphabetical Gate (`delete`), which is not a real, usable gate.
  Always pick the correct one before clicking Clone.
- **Confusing "Leanplum Variable" with the Segment link.** The field named
  `segment_list` on the Event form is labeled **Leanplum Variable** — it's
  a marketing-analytics hook, not the Segment relationship. The actual
  Segment link is the separate **SegmentID** dropdown.
- **Forgetting the Segment.** An Event with no matching Segment (or the
  wrong one) will have the wrong/blank cost and refresh behavior in-game,
  even though the Event itself saves fine.
- **Saving ≠ Deploying.** A saved record with a red ✘ under "Deployed to
  live"/"Deployed to liveops" has not reached players yet — you must run it
  through the **Process Blueprints** step above.
- **Display Name / Description show `!!SOMETHING`.** That's a
  localization placeholder, not a bug — it means no translated text has
  been linked yet. Double-click the field to create/edit the actual text
  players will see.
