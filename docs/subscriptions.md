# Brick "Subscription 1.5" — Tools Instruction Document

Covers the recurring-subscription (Subs) tool in Brick: how it works
mechanically, and a walkthrough of the five requested passes — **Manager
Pass** (priority 1), **Strap Up Pass**, **DX Army Pass**, **Ex Elite Pass**,
and **Here Comes The Money Pass**.

Investigated live against `sgs-brick-live` on 2026-08-27.

## Contents

1. [How It Works](#how-it-works)
2. [Manager Pass](#manager-pass) — Priority 1
3. [Strap Up Pass](#strap-up-pass)
4. [DX Army Pass](#dx-army-pass)
5. [Ex Elite Pass](#ex-elite-pass)
6. [Here Comes The Money Pass](#here-comes-the-money-pass-hctm)

---

## How It Works

This section is the shared reference — every pass below is built out of the
exact same three-tab record described here; each pass's section only covers
what's *different* about that pass's data.

### Where it lives

Sidebar → **Subcription & VIP** → **Subscription 1.5** → list at
`/wp_subscription/list/`.

There are three similarly-named sidebar items — easy to fat-finger the wrong
one:

| Sidebar item | What it is |
|---|---|
| Subscription | A separate, older tool — not covered here |
| **Subscription 1.5** | **This tool** — covered in this doc |
| Xsolla Subscription | Xsolla (3rd-party payment processor) subscription config — separate system |

The list page shows every Subs record in the game, including retired/cloned
test rows (`delete`, `delete_s`, `HCTM_Cloned`, `Bronze_Cloned`, `test_sub`,
etc.). The 5 passes this doc covers are live rows with real Gates:

| Pass (requested name) | Internal `Subs` name | ID | Gate |
|---|---|---|---|
| Manager Pass | `Manager` | 16 | `r42_subs` |
| Strap Up Pass | `StrapUpPass` | 15 | `r39_sub` |
| DX Army Pass | `Silver` | 11 | `r32` |
| Ex Elite Pass | `Gold` | 12 | `r32` |
| Here Comes The Money Pass | `HCTM` | 13 | `r382` |

Note DX Army Pass and Ex Elite Pass share Gate `r32` with two *other* rows in
the list (`Bronze`, and a `Bronze_Cloned` test row) — that Gate is a shared
gacha/loot-tier grouping, not unique to these two passes.

### Data model: one record, three tabs

Opening **Edit** on any row takes you to `/wp_subscription/addit/<id>/`, a
left-nav wizard with three tabs plus an unlock link:

1. **Subscription Info** — identity, popup copy, one-time signup reward
2. **Privileges Info** — repeatable list of passive perks granted for the
   life of the subscription
3. **Reward Info** — repeatable list of *recurring* rewards granted on a
   schedule while subscribed

Each tab has its own **Save** / **Save & Continue** button; the last tab also
has **Save & Unlock & Back to Subscription List**. The left-nav shows a green
check per tab once it has valid data, or a yellow warning if it's empty.

#### Tab 1 — Subscription Info

| Field | Purpose |
|---|---|
| Gate | Deployment/feature-flag key. Dropdown pulls from the *global* Gate catalog shared with every other Brick feature (RBE, Offer, etc.) — ~2,700 entries, not Subs-specific. |
| Variant | A/B test cohort targeting (`None`, `IDFA_NewUsersVarA/B`, `IDFA_ExistingUsersVarA/B`, `LCVarANewUser/BNewUser`, `PlayerLeagueA`–`E`). Also a global catalog. |
| Subs | The internal unique name for this pass (e.g. `Manager`). Plain text. |
| Web Subscription (toggle) | Tooltip: *"Turn on will make the gacha into premium loot. Premium loot grants Subscribers extra pull benefit and web currency. This should be used for paid loot gacha."* Marks this as a **web-store** subscription (as opposed to mobile IAP) and switches the linked Gacha pool into premium-loot mode. All 5 target passes have this **off** (they're mobile IAP passes) — it's only on for the `PREMIUM`/`PRESTIGE` web-sub rows. |
| Display Name | Localization string key + live preview — the popup **title** shown to players. |
| Premium 1/2/3 Desc | Three loc-key bullet points shown in the subscribe popup. |
| Rejoin Explanation | Loc key shown to a **lapsed** subscriber to encourage resubscribing. |
| Reward Items | The **one-time signup grant** — repeatable Item/Amount rows with computed HC (hard-currency-equivalent) and $ Value columns. |
| Reward Bonus Items | A second, separate one-time grant list (all 5 passes use this for `VipPoint:450`). |
| Icon Texture / 2nd Icon Texture / Signup Icon Texture | Three separate art asset paths for different UI placements of the offer popup. |
| Background / Normal Carousel | Optional background art + home-screen carousel slot. |

#### Tab 2 — Privileges Info

A repeatable list (**+ Add Privileges**) of passive perks. Each entry:

| Field | Purpose |
|---|---|
| ID | Read-only, auto-assigned |
| Type | Dropdown — see catalog below |
| Value | Meaning depends on Type: boolean flag, percent/count, or a foreign-key ID string |
| Is Visible | Whether this perk is **shown** in the in-game subscription-details UI. A privilege can be mechanically defined but hidden — see [Manager Pass](#manager-pass) for a concrete example of this being used for dormant/future tiers. |
| Display Name / Description | Loc keys, only relevant when Is Visible |
| Icon Texture | Art asset |

**Privilege Type catalog** (14 values, global dropdown — same list on every
pass):

| Type | Meaning | Confidence |
|---|---|---|
| `healthpack_boost_percent` | Boosts health-pack recovery amount by N% | Confirmed via tooltip ("Boost HP recover") |
| `vip_point_bonus_percent` | Bonus VIP points earned per purchase | Confirmed via tooltip ("Bonus vip point when purchasing") |
| `lootbox_bonus_number` | N bonus loot boxes per battle | Confirmed via tooltip ("Bonus lootbox in battle") |
| `clear_ticket_bonus_number` | Grants auto-clear tickets on a schedule; Value is a 3-part string (e.g. `0,0,0`) | Confirmed via tooltip ("Gain clear ticket on period of time"); exact 3-field meaning not verified |
| `entourage_loadout_unlock` | Unlocks extra Entourage loadout slot(s); Value hint says "1 = true / 0 = false" but multi-value tiers were observed (see Manager Pass) | Confirmed via tooltip ("Unlock entourage loadout") |
| `pve_access` | Grants access to a specific PVE chapter/tournament (Value = chapter/book ID, e.g. `FQA_DATDQ_BOOK_02`) | Inferred from field name + observed values |
| `sgss_access` | Unlocks a specific Superstar (Value = Superstar ID, e.g. `SS_HHH_DX`) | Inferred from field name + observed values |
| `fc_access` | Grants Fight Card VIP-tier access (Value observed as `fc_vip`) | Inferred from field name + observed values |
| `champions_club_access` | Grants access to the Champions Club VIP room | Inferred from name |
| `premium_manager_reward` | Manager-Pass-specific reward flag | Inferred from name; only used on Manager Pass |
| `gold_league_loot_coin` | One-time Gold League Loot Coin bonus | Inferred from name; only used on Manager Pass |
| `premium_gacha` | Converts a Gacha pool to premium loot for subscribers | Inferred from the Web Subscription tooltip wording |
| `pity_pull_gacha` | Grants a guaranteed/pity Gacha pull | Inferred from name; not observed configured on any of the 5 target passes |
| `web_shop_access` | Grants access to the web store | Inferred from name; not observed configured on any of the 5 target passes |

Where a row says "Inferred," it means: the effect wasn't spelled out anywhere
in the UI (no tooltip) — treat it as a strong guess to verify with engineering
before relying on it in a spec.

#### Tab 3 — Reward Info

A repeatable list (**+ Add New Rewards**) of **recurring** rewards granted on
a schedule while the subscription stays active — separate from the one-time
signup reward in Tab 1. Each entry:

| Field | Purpose |
|---|---|
| Reward ID | Read-only, auto-assigned |
| Is Visible | Same meaning as Tab 2 |
| Display Name / Description | Loc keys |
| Repeat Schedule | An [RRULE](https://icalendar.org/iCalendar-RFC-5545/3-3-10-recurrence-rule.html) string, e.g. `RRULE:FREQ=DAILY;INTERVAL=7` (every 7 days / weekly) or `RRULE:FREQ=DAILY` (every day). A checkbox mirrors it in plain English ("Repeats every N days"); the **Edit** button opens a recurrence-rule picker. |
| Reward Items | Same Item/Amount/HC/$ table as Tab 1 |

Not every pass uses this tab — Manager Pass currently has it completely
empty (no recurring reward configured at all); Strap Up Pass has two
(a weekly and a daily grant). See each pass's section for specifics.

---

## Manager Pass

**Priority 1** — this pass is the candidate for a possible Battlepass
upgrade by the feature team. This section is the "how does this actually
work today" reference for that work.

- Record ID: **16**
- Internal `Subs` name: **`Manager`**
- Gate: **`r42_subs`**
- Edit URL: `/wp_subscription/addit/16/`

### Tab 1 — Subscription Info

| Field | Value (loc key) | Live preview text |
|---|---|---|
| Display Name | `!!R42_SUB_POPUP_TITLE` | **MANAGER'S PASS** |
| Premium 1 Desc | `!!R42_SUB_POPUP_1` | 2X SPEED UP Perks for Faction Feuds |
| Premium 2 Desc | `!!R42_SUB_POPUP_2` | ACCESS TO ENTOURAGE LOADOUTS |
| Premium 3 Desc | `!!R42_SUB_POPUP_3` | EXCLUSIVE Loot with a Chance at Mr. Perfect "nWo" |
| Rejoin Explanation | `!!R42_SUB_POPUP_LAPSEDSUB` | KEEP THOSE GOLD LEAGUE LOOT COINS COMING! |

- Web Subscription toggle: **off** (this is a mobile IAP pass, not a web-store one)
- Variant: `None`

**One-time signup reward** (granted once, on first purchase):

| List | Item | Amount | HC | $ Value |
|---|---|---|---|---|
| Reward Items | `PremiumLeagueToken` | 10,000 | 0 | 0 |
| Reward Bonus Items | `VipPoint` | 450 | 900 | 9 |

Art: Icon Texture `UI/R42/Subs/Sub_pop_up_offer_2`, 2nd Icon Texture
`UI/Currency/League_Gacha_premium_reward`, Signup Icon Texture
`UI/R42/Subs/Sub_pop_up_offer_1`. Background and Normal Carousel are unset.

### Tab 2 — Privileges Info

Nine privilege entries exist today:

| # | Type | ID | Value | Visible | Display Name / Description |
|---|---|---|---|---|---|
| 1 | `premium_manager_reward` | — | 0 | ✅ | "PREMIUM MANAGER'S REWARDS" / "Receive 10000 Gold Loot Coins" |
| 2 | `gold_league_loot_coin` | — | 0 | ✅ | "ONE TIME SIGN UP BONUS" / "10000 Gold League Loot Coins" |
| 3 | `entourage_loadout_unlock` | 83 | **1** | ✅ | "ENTOURAGE LOADOUTS!" / "Additional Entourage Loadouts for every Superstar!" |
| 4 | `healthpack_boost_percent` | 84 | 0 | ✅ | "BOOSTED HEALTH PACKS" / "Each Health Pack will heal for more!" |
| 5 | `vip_point_bonus_percent` | 85 | 0 | ✅ | "VIP POINTS BOOST" / "Earn more VIP Points with every Store purchase!" |
| 6 | `lootbox_bonus_number` | 86 | 0 | ✅ | "BONUS LOOT BOXES" / "Get even more Loot Boxes after every victory!" |
| 7 | `clear_ticket_bonus_number` | 82 | `0,0,0` | ✅ | "AUTOCLEAR TICKETS" / "Autoclear matches for instant loot!" |
| 8 | `entourage_loadout_unlock` | 83 | **2** | ❌ hidden | (same loc keys as #3) |
| 9 | `entourage_loadout_unlock` | 84 | **3** | ❌ hidden | (same loc keys as #3) |

#### The closest thing to an existing "path/tier" system

Entries **#3, #8, #9** are the same privilege type
(`entourage_loadout_unlock`) repeated at three different Values — **1, 2,
3** — but only the first (Value 1) is marked visible. This looks like a
dormant 3-tier progression that was scaffolded into the data and then never
finished/wired up: the data model already supports "grant tier N of this
perk," it's just that tiers 2 and 3 are switched off. If the Battlepass
rework wants a tiered-privilege structure, this is the one existing pattern
to study or build on — worth asking whoever added these (likely part of the
original Manager Pass build) whether tiers 2/3 were ever intended to
activate on renewal months, or are leftover scaffolding.

#### Everything else is configured but inert

The four "boost" privileges (`healthpack_boost_percent`,
`vip_point_bonus_percent`, `lootbox_bonus_number`, and the numeric part of
`clear_ticket_bonus_number`) are all set to **Value 0** — i.e., the perk
exists, is visible, and has real display copy, but mechanically grants
nothing right now. That could be intentional (display-only perks, or
placeholders while the real values are tuned elsewhere) or an oversight —
flag this to whoever owns the numbers before assuming either way.

### Tab 3 — Reward Info

**Empty.** Manager Pass has no recurring reward configured at all — compare
to [Strap Up Pass](#strap-up-pass), which has a weekly + a daily recurring
grant. If the Battlepass upgrade wants periodic (weekly/monthly) reward
drops for subscribers, this tab is exactly where that would go, and Strap Up
Pass's setup is the template to copy.

### How to edit this record (step-by-step)

1. Go to **Subcription & VIP → Subscription 1.5** in the sidebar.
2. Find the row with `Subs = Manager` (Gate `r42_subs`), click the **Edit**
   (pencil) icon.
3. If a popup says someone else is currently editing this record, click
   **Back to list** and check with them first, rather than forcing your way
   in.
4. **Subscription Info** tab: edit popup copy (loc keys), the one-time
   signup reward table, and art paths here. Click **Save & Continue** to
   move to the next tab (or **Save** to stay).
5. **Privileges Info** tab: click **+ Add Privileges** to add a new perk —
   pick a Type from the dropdown, set Value, toggle Is Visible, fill in the
   Display Name/Description loc keys and Icon Texture. Click the trash icon
   on a card to remove it.
6. **Reward Info** tab: click **+ Add New Rewards** to add a recurring
   grant — set the Repeat Schedule via the **Edit** button (opens an RRULE
   picker), then add Reward Items same as elsewhere.
7. When done, use **Save & Unlock & Back to Subscription List** on the
   final tab — this both saves and releases your edit-lock so the next
   person doesn't see you as still "in" the record.
8. If you need to stop partway through without saving, use **Unlock & Back
   to list** in the left nav — don't just close the tab, or your lock stays
   assigned until someone force-acquires it.

---

## Strap Up Pass

This pass is the most fully-built-out of the five (all three tabs
populated) — useful as a reference example, e.g. for what a filled-in
Reward Info tab looks like for [Manager Pass](#manager-pass).

- Record ID: **15**
- Internal `Subs` name: **`StrapUpPass`**
- Gate: **`r39_sub`**
- Edit URL: `/wp_subscription/addit/15/`

### Tab 1 — Subscription Info

| Field | Value (loc key) | Live preview text |
|---|---|---|
| Display Name | `!!R39_STRAP_POPUP_TITLE` | **STRAP UP PASS** |
| Premium 1 Desc | `!!R39_STRAP_POPUP_1` | INCREASED CHANCE to level up Medals |
| Premium 2 Desc | `!!R39_STRAP_POPUP_2` | RENEWAL BONUS: 100 MONTHLY SKILL PLATE CHIPS |
| Premium 3 Desc | `!!R41_STRAP_POPUP_4` | Daily Strap Parts and Weekly Medal Bits |
| Rejoin Explanation | `!!R39_STRAP_POPUP_LAPSEDSUB` | Keep those Medals and Straps coming! |

Web Subscription: off. Variant: `None`.

**One-time signup reward:**

| List | Item | Amount | HC | $ Value |
|---|---|---|---|---|
| Reward Items | `EpicVIPStableStrap_Token` | 1 | 9,999 | 99.99 |
| Reward Items | `GrabBag_Strap_Epic_Random_Male_Token` | 4 | 564 | 5.64 |
| Reward Items | `BagToken_Tier4_Random` | 16 | 16,000 | 160.00 |
| **Reward Items total** | | | **26,563** | **265.63** |
| Reward Bonus Items | `VipPoint` | 450 | 900 | 9 |

Art: Icon Texture `UI/StoreV2/OfferImages/SUB_StrapUp_top_items_01`, 2nd Icon
Texture `UI/Misc/Icon_StrapUpPass`, Signup Icon Texture
`UI/GrabBags/SUB_StrapUp_bottom_item_01`.

### Tab 2 — Privileges Info

| Type | Value | Visible | Display Name / Description |
|---|---|---|---|
| `vip_point_bonus_percent` | 0 | ✅ | "VIP POINTS BOOST" / "Earn more VIP Points with every Store purchase!" |
| `healthpack_boost_percent` | 0 | ✅ | "BOOSTED HEALTH PACKS" / "Each Health Pack will heal for more!" |
| `pve_access` | `tour_king_weekly` | ✅ | grants access to the "tour_king_weekly" PVE content |
| `fc_access` | `fc_vip` | ✅ | grants Fight Card VIP-tier access |
| `clear_ticket_bonus_number` | `0,0,0` | ✅ | "AUTOCLEAR TICKETS" / "Autoclear matches for instant loot!" |

Same "configured but Value 0" pattern as Manager Pass for the two boost
percentages — likely a general convention across passes rather than
something specific to Strap Up.

### Tab 3 — Reward Info

Two recurring rewards, both visible:

| Schedule (RRULE) | Cadence | Display Name / Description | Reward |
|---|---|---|---|
| `RRULE:FREQ=DAILY;INTERVAL=7` | Every 7 days | "Weekly Medal Bits!" / "Take your Medals to the next level!" | `StrapPass_MedalBits_Token` x1 (HC 9,999 / $99.99) |
| `RRULE:FREQ=DAILY` | Every day | "Daily Strap Parts!" / "Reinforce your Straps to earn boosts!" | `StrapPass_StrapParts_Token` x1 (HC 9,999 / $99.99) |

This is the pattern to copy if Manager Pass's empty Reward Info tab gets
filled in as part of the Battlepass work.

### How to edit

Same generic procedure as
[Manager Pass → "How to edit this record"](#how-to-edit-this-record-step-by-step);
just start from the `StrapUpPass` row (Gate `r39_sub`) on the Subscription
1.5 list instead.

---

## DX Army Pass

- Record ID: **11**
- Internal `Subs` name: **`Silver`** (the requested name "DX Army Pass" is
  the player-facing branding — the internal record and its icon assets both
  say "Silver" / "DX Army")
- Gate: **`r32`** — shared with `Bronze` and Ex Elite Pass (`Gold`); this
  Gate groups a whole DX/King-of-Kings gacha tier, it isn't unique to this
  one pass.
- Edit URL: `/wp_subscription/addit/11/`

> **Coverage note:** the preview text for Tab 1's messages and the Tab 3
> (Reward Info) details weren't captured for this pass yet — check directly
> in the tool before relying on them.

### Tab 1 — Subscription Info (loc keys only — preview text not pulled)

| Field | Loc key |
|---|---|
| Display Name | `!!R32_SUBS_SILVER` |
| Premium 1 Desc | `!!R32_SUBS_SILVER_CONTENT_1` |
| Premium 2 Desc | `!!R32_SUBS_SILVER_CONTENT_2` |
| Premium 3 Desc | `!!R32_SUBS_SILVER_CONTENT_3` |

**One-time signup reward:**

| List | Item | Amount |
|---|---|---|
| Reward Items | `Poster_ShawnMichaels_DX_2Star_Gold` | 1 |
| Reward Items | `GrabBagToken_DX_Army` | 1 |
| Reward Bonus Items | `VipPoint` | 450 |

Art: Icon Texture `UI/WrestlersPortraitBig/PortraitFull_ShawnMichaels_DX`,
2nd Icon Texture `UI/Misc/icon_SubGroup_02`, Signup Icon Texture
`UI/GrabBags/DX_ArmyPass`.

### Tab 2 — Privileges Info

| Type | Value | Display Name / Description |
|---|---|---|
| `sgss_access` | `SS_ShawnMichaels_DX` | unlocks the Shawn Michaels DX Superstar |
| `fc_access` | `fc_vip` | grants Fight Card VIP-tier access |
| `healthpack_boost_percent` | 0 | (see catalog above) |
| `lootbox_bonus_number` | 0 | (see catalog above) |
| `vip_point_bonus_percent` | 0 | (see catalog above) |
| `pve_access` | `FQA_DATDQ_BOOK_02` | grants access to PVE book/chapter `FQA_DATDQ_BOOK_02` |
| `clear_ticket_bonus_number` | `0,0,0` | (see catalog above) |

Note the shape is very close to Strap Up Pass's privilege list
(`sgss_access` here plays the same role `pve_access`+`fc_access` play there:
this pass's headline perk is unlocking a specific Superstar rather than a
PVE tour), plus the same four "boost" privileges all sitting at Value 0.

### Tab 3 — Reward Info

**Not verified in this pass of research** — please check directly in the
tool before assuming it's empty like Manager Pass or populated like Strap Up
Pass.

### How to edit

Same generic procedure as
[Manager Pass → "How to edit this record"](#how-to-edit-this-record-step-by-step);
start from the `Silver` row (Gate `r32`) on the Subscription 1.5 list.

---

## Ex Elite Pass

- Record ID: **12**
- Internal `Subs` name: **`Gold`** (player-facing branding "Ex Elite Pass" —
  internal record and icon assets say "Gold" / "DX Elite")
- Gate: **`r32`** — shared with `Bronze` and DX Army Pass (`Silver`); a
  grouping Gate, not unique to this pass.
- Edit URL: `/wp_subscription/addit/12/`

> **Coverage note:** same as [DX Army Pass](#dx-army-pass) — Tab 1's live
> preview text and Tab 3 (Reward Info) weren't captured for this pass yet.

### Tab 1 — Subscription Info (loc keys only — preview text not pulled)

| Field | Loc key |
|---|---|
| Display Name | `!!R32_SUBS_GOLD` |
| Premium 1 Desc | `!!R32_SUBS_GOLD_CONTENT_1` |
| Premium 2 Desc | `!!R32_SUBS_GOLD_CONTENT_2` |
| Premium 3 Desc | `!!R32_SUBS_GOLD_CONTENT_3` |

**One-time signup reward:**

| List | Item | Amount |
|---|---|---|
| Reward Items | `Poster_HHH_DX_3Star_Bronze` | 1 |
| Reward Items | `GrabBagToken_DX_Elite` | 1 |
| Reward Bonus Items | `VipPoint` | 450 |

Art: Icon Texture `UI/WrestlersPortraitBig/PortraitFull_HHH_DX`, 2nd Icon
Texture `UI/Misc/icon_SubGroup_03`, Signup Icon Texture
`UI/GrabBags/Grabbag_DX_ElitePass`.

### Tab 2 — Privileges Info

| Type | Value | Display Name / Description |
|---|---|---|
| `sgss_access` | `SS_HHH_DX` | unlocks the Triple H (HHH) DX Superstar |
| `pve_access` | `FQA_DATDQ_BOOK_03` | grants access to PVE book/chapter `FQA_DATDQ_BOOK_03` |
| `lootbox_bonus_number` | **2** | grants 2 bonus loot boxes per battle — the only non-zero "boost" value observed across all 5 target passes |
| `clear_ticket_bonus_number` | `0,0,0` | (see catalog above) |
| `healthpack_boost_percent` | 0 | (see catalog above) |
| `vip_point_bonus_percent` | 0 | (see catalog above) |
| `fc_access` | `fc_vip` | grants Fight Card VIP-tier access |

Structurally this is DX Army Pass's privilege list one tier up (a different
Superstar + a later PVE book), plus it's the one place across all 5 passes
where a "boost" privilege actually has a non-zero Value
(`lootbox_bonus_number = 2`) — worth double-checking whether that's
intentional tuning or a stray edit, since every equivalent field on every
other pass is 0.

### Tab 3 — Reward Info

**Not verified in this pass of research** — please check directly in the tool.

### How to edit

Same generic procedure as
[Manager Pass → "How to edit this record"](#how-to-edit-this-record-step-by-step);
start from the `Gold` row (Gate `r32`) on the Subscription 1.5 list.

---

## Here Comes The Money Pass (HCTM)

- Record ID: **13**
- Internal `Subs` name: **`HCTM`**
- Gate: **`r382`**
- Edit URL: `/wp_subscription/addit/13/`

There is also a **`HCTM_Cloned`** row (ID 14, Gate `delete`) in the list —
looks like a retired clone/test copy, not a second live pass. Make sure any
edits target ID 13, not 14.

> **Coverage note:** same as DX Army/Ex Elite — Tab 3 (Reward Info) wasn't
> captured for this pass yet.

### Tab 1 — Subscription Info

| Field | Value (loc key) |
|---|---|
| Display Name | `!!R382_HCMP_POPUP_TITLE` |
| Premium 1 Desc | `!!R382_HCMP_POPUP_1` |
| Premium 2 Desc | `!!R382_HCMP_POPUP_2` |
| Premium 3 Desc | `!!R382_HCMP_POPUP_3` |
| Rejoin Explanation | `!!R382_HCMP_POPUP_LAPSEDSUB` |

(Live preview text for these keys wasn't pulled in this pass — check
directly in the tool, same caveat as DX Army/Ex Elite.)

**One-time signup reward:**

| List | Item | Amount |
|---|---|---|
| Reward Items | `Poster_Sting_Crow_2Star_Bronze` | 1 |
| Reward Items | `SoftCurrency` | 250,000 |
| Reward Bonus Items | `VipPoint` | 450 |

Art: Icon Texture `UI/StoreV2/OfferImages/HCTM_membership_reward`, 2nd Icon
Texture `UI/Misc/Icon_Money_Clip`, Signup Icon Texture
`UI/GrabBags/HCTM_Pass`. This is also the only one of the 5 target passes
with a **Normal Carousel** slot set: `UI/SidebarLinks/Offer_HomeScreen_R382`.

### Tab 2 — Privileges Info

| Type | Value | Display Name / Description |
|---|---|---|
| `champions_club_access` | 0 | grants access to the Champions Club VIP room |
| `lootbox_bonus_number` | 0 | (see catalog above) |
| `clear_ticket_bonus_number` | `0,0,0` | (see catalog above) |
| `healthpack_boost_percent` | 0 | (see catalog above) |
| `vip_point_bonus_percent` | 0 | (see catalog above) |

HCTM is the only one of the 5 target passes that uses
`champions_club_access` — its headline non-currency perk is the VIP room
rather than a Superstar unlock (DX Army/Ex Elite) or PVE/FC access (Strap
Up). Its money-themed reward is otherwise a large `SoftCurrency` grant
(250,000) rather than a rare item like the other passes.

### Tab 3 — Reward Info

**Not verified in this pass of research** — please check directly in the tool.

### How to edit

Same generic procedure as
[Manager Pass → "How to edit this record"](#how-to-edit-this-record-step-by-step);
start from the `HCTM` row (Gate `r382`, ID 13 — not the `HCTM_Cloned` row)
on the Subscription 1.5 list.
