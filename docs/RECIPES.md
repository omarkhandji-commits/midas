# MIDAS Recipes

These recipes are operator workflows. They do not promise revenue. Each mutating
step remains approval-gated.

## 1. First Paid Offer Draft

Goal: turn a niche into an offer, landing draft, and approval card.

```bash
midas earn "local accountants who need faster invoice follow-up"
midas approvals list
midas approvals approve <id>
midas execute <id>
```

Output: receipted scan, prepared landing artifact, approval metadata, and an
execution receipt if approved.

## 2. Proof-First Outreach

Goal: prepare outreach without sending anything automatically.

```bash
midas earn "B2B SaaS founders with stale onboarding emails"
midas approvals list
```

Review the proposed email or sequence in the Approval Center. Reject anything
that lacks evidence, consent, or a specific business reason.

## 3. Content Asset Batch

Goal: create content scaffolds cheaply before involving a stronger model.

```bash
midas blog-lint posts/draft.md
midas course "Email onboarding for solo SaaS founders" --modules 5
midas capabilities plan "turn this into a short video with voice"
```

Use `video.script`, `video.storyboard`, `image.draft`, and
`remotion.project.draft` from the agent loop when you need approval-gated media
files.

## 4. Scheduled Social Queue

Goal: prepare posts ahead of time and queue due posts for approval.

```bash
midas schedule recipe "freelance developers" --at 09:00
midas drain
```

`midas drain` never publishes directly. It moves due posts into approvals.

## 5. Outcome And ROI Review

Goal: connect cost receipts to real operator-recorded outcomes.

```bash
midas roi
midas outcome record <run_id> "Client paid invoice" -m revenue=500
midas roi
midas proof export proof.html --run-id <run_id>
```

Cost comes from signed receipts. Revenue comes only from explicit outcome
records.
