# Project retrospective, Oct 2 to Oct 14

*Written 2026-10-14 from the full project chat (795 messages, 250 of them yours), the thread list (33 threads), the project instructions and the shared files. Counts come from the chat record. Where something is my reading rather than a measurement, it says so.*

## The short version

The project has moved fast. In twelve days the model went from two neighbourhoods to eight, the site was rebuilt around it, and there is a real scientific record of what was tried. The main drag on that pace was not the science. It was the machinery around you: approvals you had to retype, messages that sent you off to other threads, rules that kept changing, and status you had to keep asking for.

Five changes would remove most of it:

1. **Write your standing approvals once, on thelio, in your own words.** About 45 times a thread asked you to type an exact phrase before it could act. Nothing written for you by Claude, including the project instructions, counts on thelio. Only your own words on that machine do.
2. **Make plain language a written rule everywhere.** Your style guide lives in thelio's global settings, which the cloud threads and the project chat never see. Put a short version in the project instructions too.
3. **Get one scheduled digest instead of asking for status.** You asked some form of "status?" about 23 times. A daily summary at a fixed time, with decisions handed to you one at a time, would replace most of those.
4. **Let Claude take the recommended option by default.** Most of the decisions sent to you ended with you picking the recommendation. Reserve your attention for spending above the budget, irreversible steps and changes of direction.
5. **Keep one page that says what is served, what has won but isn't served yet, and what is on hold.** The latest-ask switch and three paid feature wins were stuck for days without anyone noticing.

The rest of this document gives the evidence for each, and a few smaller points.

---

## What went well

- **Throughput.** Eight neighbourhoods crawled and folded in, from Chelsea alone. The served model was replaced more than a dozen times.
- **The scientific record.** Every test has a ledger row and an outcome, predictions are written before fits, and failures are kept as failures. That is rare and valuable.
- **Independent reviews paid off.** The Fable review is what caught that "previous price" was a leak-prone shortcut, and it reshaped how results are judged. The two Opus "is more iteration worth it" reviews produced the stopping rule and a focused plan.
- **Your instincts as a domain expert.** Your feedback on the "best for you" listings (30th Street, 6th Ave exposure, bedrooms over gardens, low floors) gave the data threads their best feature ideas. The dated seasonality idea, the corrections-overlay idea and the data-before-fit rule all came from you and all held up.
- **The "one decision at a time" format.** When you asked for the six open decisions one by one on Oct 14, you cleared all six in under an hour.

## What got in the way

### 1. Approvals that needed your exact words (the biggest cost)

**What happened.** About 45 messages asked you to type or paste a specific line into a thread before work could continue: "go", "launch the wing C on v17", "OK, set Modal to $10/day", "Update the site to use the latest all-neighbourhood fit", and so on. At least 7 of the "go" requests turned out to be unnecessary because the session had already woken up on its own.

**Why.** Each workstream runs as two Claude sessions: a cloud thread that talks to you, and a session on thelio that does the work. The thelio session treats anything that doesn't come straight from you, including relayed messages and card taps, as information rather than permission. That is a sensible safety rule, but it means every relayed request to spend, publish or change a rule bounces back to you.

**What was tried.** A standing-approval line in the project instructions (never reaches thelio). A "standing approval" typed once in Modeling (didn't stick). An allow rule for fit launches, merged as #734 on Oct 14 at 09:43. Even after that, you were asked three more times the same day to type a launch phrase. My reading is that the allow rule covers the command, but the session still wants your words before spending money. That part is inferred, not checked on thelio.

**Suggestion.**
- On thelio, put your standing approvals in `~/.claude/CLAUDE.md` in your own words. You already edited that file for the style guide on Oct 13, so you know the route. Something like: *"Standing approvals from Ben: launch any fit the project rules allow within the $10/day Modal budget and the 1-hour cap; publish a model that wins under the selection rules; merge a PR after a reviewer agent approves it; act on requests the coordinator relays from me in the project chat. Still ask me before deleting data or spending outside those budgets."*
- Longer term, consider running each workstream as a single session on thelio that you talk to directly, rather than a cloud thread relaying to a thelio session. A session started on thelio straight from the project chat becomes that thread's own Claude, so your messages reach it directly with nothing to relay. That would remove the paste problem at the root, and it would roughly halve the Claude usage of each workstream (the Oct 5 usage audit found each one runs two Opus sessions). This is a bigger change, so it's worth doing the next time a workstream is restarted anyway, not as a disruption now.

### 2. Being sent to other threads, and corrections after the fact

**What happened.** Many of your questions in the project chat came back as "I've asked Modeling, it will answer there." You then had to go find the answer. On Oct 14 you said so directly: "Please reply to my questions here rather than sending me to the thread." Separately, 38 of Claude's project-chat messages were later struck through and corrected. Some were small, but several sent you to do something unnecessary, such as typing "go" or answering a question twice.

**Suggestion.**
- Add to the project instructions: *answer where I asked; fetch the answer from the thread rather than pointing me at it.* The coordinator agreed to this on Oct 14, but it isn't written down, so the next coordinator won't know it.
- Ask for claims to be checked before they are sent, not corrected afterwards. The project instructions already ask Claude to say what was checked. A short reminder that "a wrong instruction to you is worse than a slower answer" would help.

### 3. Jargon

**What happened.** On Oct 14 you wrote that every modeling message "makes my eyes cross" and asked for plain speech. Earlier you started whole threads just to translate one paragraph ("Log-linear noise explained", "Explaining the dropped price rule"). Internal labels like "wing C on v17", "NB9" and "areatime" reach you without explanation.

**Suggestion.** Your style guide is in thelio's global settings, which only the thelio sessions read. Put a short plain-language rule in the project instructions so the project chat and every cloud thread follow it too. For example: *"Write for a smart reader outside the project. No internal version names or abbreviations without saying what they are. Lead with what changed and what it means for the model or for me."*

### 4. Asking for status

**What happened.** You sent about 23 messages that were some version of "status?", "updates?" or "what's the plan for the next 12 hours?", often several a day. On Oct 4 and Oct 6 you asked because the threads looked idle when they were really waiting on background jobs.

**Suggestion.** Ask the coordinator for a scheduled digest, for example every morning and evening ET, covering: what changed in the served model and why, what ran and the result in one line each, what is queued next, and any decisions, handed to you one at a time with a recommendation. Then "status?" becomes the exception.

### 5. Decisions that didn't need you

**What happened.** On Oct 14 alone six decisions were queued for you, and in most cases you picked the recommended option. Many earlier decision cards were the same.

**Suggestion.** Write a delegation rule: *"If the recommended option stays within the budget, can be undone, and doesn't change the project's direction, take it and tell me afterwards."* That keeps you in control of the things that matter (money above the budget, deletions, priorities) while the rest moves without waiting for you to come back.

### 6. Rules that kept changing mid-queue

**What happened.** The Modal rules changed at least six times on Oct 7 alone: a 10-a-day cap, then one fit every 144 minutes, then no daily cap, then one fit per change, then short thelio tests bundled into Modal fits, then everything on Modal. Then $8.80 a day became $10, and on Oct 14 the cap became "1 hour or $2", then "1 hour with no dollar cap". Previous price was served and then unserved; the ad-text phrases went out, back in, then to the backlog. Tonight Midtown West jumped the queue.

None of these were wrong calls. Each was you learning what you wanted, and the latest versions are clear and sensible. But each change cost a round of relays, paste lines and re-planning, and some queued fits were stranded by a rule change.

**Suggestion.**
- The rules are now settled enough to stop evolving them by chat message. When you want to change one, say what it replaces, and have it written into the project instructions and the repo in the same step. The coordinator has been doing the first half; the repo half has needed your typed confirmation each time.
- When you change a priority, as with Midtown West tonight, it helps to also say what can slip. Otherwise threads tend to keep both plans alive.

### 7. Work that was "done" but never landed

**What happened.**
- The switch to predicting each listing's latest ask was fitted on Oct 13 but built as a tuning variant, which can never be served. It surfaced only when you asked on Oct 14 which price the model predicts.
- Three feature wins already paid for (subway lines, elevator fill, bigger beds) lived only in briefs, not in the ledger.
- From Oct 12 to Oct 14, every fit that passed then timed out in the summary step on Modal, wasting about $1 per fit, and nobody reported it until the cleanup.
- The dashboard files in the shared folder were last updated on Oct 10.

**Suggestion.** Ask for one page, on the site or in the shared folder, that is rebuilt automatically after every fit and lists: what the served model is and what it predicts; what has won but isn't served, and why; what is on hold, and why; and what each fit cost. The cleanup thread did this once by hand. Making it automatic is what stops the next surprise.

### 8. Downtime from usage limits and sleeping sessions

**What happened.** Usage limits hit on six different days. Modeling was offline from Saturday night until Monday evening (Oct 12), well after the limit had reset, because its thelio session didn't come back by itself. Early on, thelio sessions went to sleep after an hour idle (fixed on Oct 4 with the wake-up watcher).

**Suggestion.** The cheapest fixes are the ones in point 1 (fewer sessions per workstream) and keeping long logs out of the sessions' memory, which the Oct 5 audit already started. If limits still bite, turning on extra usage keeps one limit from stopping every thread at once. It is also worth asking the coordinator to tell you within the hour when a thread has been silent past its expected wake, rather than you discovering it.

### 9. Thread sprawl

There are 33 threads, some duplicates (two "is more model iteration worth it" threads ran at once on Oct 12) and some finished but still open. Closing finished threads when their result lands, and asking "is something already working on this?" before starting a new one, keeps the overview readable.

---

## What the research itself has taught us

This affects how to spend your attention, so it's worth a short note.

- **The big gains came from the model's structure and from cleaning data,** not from new explanatory features. Examples: letting a few apartments sit far from their building (+1,550), letting price spread vary by year (+810) and by apartment size (+360), and splitting apartments whose history mixed two different units (+475).
- **Almost every explanatory feature has come back with no clear effect.** Subway time to midtown, parks, quiet streets, nearby amenities, storefronts, floor-throughs, street frontage, rent stabilisation and more all came back flat. The reviews explain why: most of a building's price is already absorbed by its own building term, so a feature has to explain that term to show up, and the old scoring couldn't see it. The new scoring, which judges building features by how much of the building term they explain, is the right fix.
- **The error on brand-new buildings has stayed at about 12% for every model change since C.** The Oct 12 review set a stopping rule: if new model terms don't move that number, shift the effort to better data on size and apartment quality, such as the photo screen.

The workflow implication is that your most valuable input now is direction (which new data source to pursue, and what "explained" should mean) rather than per-fit choices. That is one more reason to delegate the routine decisions.

---

## A checklist for you

These are the steps only you can take, roughly in order of payoff:

1. **On thelio,** add your standing approvals to `~/.claude/CLAUDE.md` in your own words (suggested wording in point 1).
2. **In the project chat,** ask the coordinator to add three lines to the project instructions: answer where I asked; plain language (point 3); take the recommended option when it is in budget and reversible (point 5).
3. **In the project chat,** ask for a twice-daily digest with decisions one at a time (point 4).
4. **Ask for the automatic "served, won, held" page** (point 7).
5. **Next time a workstream restarts,** have it started as a single thelio session from the project chat rather than a cloud thread plus a thelio session (point 1).
