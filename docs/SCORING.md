# MIDAS — Opportunity Scoring (/100)

Every opportunity is scored before it competes for your time. The score is transparent: the
agent always shows the per-factor breakdown and names the single weakest factor.

## Weights (sum = 100)
| Factor | Weight | 0 = bad … 10 = great |
|---|---:|---|
| Real market demand | 15 | nobody wants it … proven, urgent pain |
| Speed to first cash | 12 | months … days |
| MRR / recurrence potential | 15 | one-off … sticky subscription |
| Low support burden | 10 | constant hand-holding … near-zero support |
| Defensibility (hard to copy) | 8 | trivial clone … real moat |
| Low competition | 7 | red ocean … open lane |
| Distribution (a channel you can reach) | 10 | no audience … existing distribution |
| Low launch cost | 6 | expensive … near-free |
| Low launch time | 7 | long build … ship this week |
| Low risk (legal/tech/reputation) | 5 | risky … safe |
| Operator fit (your tools/skills) | 5 | foreign … squarely in your wheelhouse |

**Score = Σ (factor_value/10 × weight).** Range 0–100.

## Bands
- **75–100 → BUILD.** Propose it as the next move.
- **60–74 → WATCHLIST.** Keep, re-score weekly as evidence arrives.
- **< 60 → ARCHIVE.** Don't spend tokens or time on it.

## Hard gates (auto-fail to ARCHIVE regardless of score)
- Requires spam, deception, or guaranteed-income claims.
- Legally gray or PII-scraping dependent.
- Structurally high support (you'd become tech support forever).
- Can't be reached by any distribution channel you have.

## Worked example
> *Niche AI "meeting-notes → CRM" sync for solo consultants*
> demand 8·15=12.0 · speed 7·12=8.4 · MRR 9·15=13.5 · low-support 6·10=6.0 ·
> defensibility 5·8=4.0 · low-competition 5·7=3.5 · distribution 7·10=7.0 ·
> low-cost 8·6=4.8 · low-launch-time 6·7=4.2 · low-risk 8·5=4.0 · fit 8·5=4.0
> **Total ≈ 71.4 → WATCHLIST.** Weakest factor: defensibility — needs a wedge (a specific
> integration or vertical) before it graduates to BUILD.

## Notes
- Re-score weekly; demand/competition shift.
- The CFO sub-agent owns this score and ties it to the live P&L: a high score with a bad
  cost-to-first-cash ratio still loses to a slightly lower score that pays this week.
- Learned taste: the Curator nudges weights toward what the operator actually approves over
  time (e.g., if you keep rejecting high-support ideas, low-support weight effectively rises).
