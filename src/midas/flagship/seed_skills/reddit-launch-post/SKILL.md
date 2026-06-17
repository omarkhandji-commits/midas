# reddit-launch-post — Reddit launch post (sub-aware)

**When to use.** The operator wants to launch (or relaunch) a product
on a relevant subreddit without getting mod-banned in the first hour.

**Pre-flight — non-negotiable.**
1. Read the sub's rules. Most cash-relevant subs (r/Entrepreneur,
   r/SideProject, r/SmallBusiness, r/startups) require karma + age + a
   self-promotion ratio (90/10 contribute-vs-promote). If the operator
   doesn't meet those, STOP and recommend posting in r/SideProject or
   r/IMadeThis where the bar is lower.
2. Check whether the sub has a sticky "Promote your project" mega-thread.
   If yes, the launch goes there, NOT a new post.

**Inputs.**
- Target subreddit (the agent reads the rules; if missing or sub is
  inactive, STOP).
- Product 1-paragraph description
- Launch URL (live, not coming-soon)
- What the operator wants from Reddit: feedback / first users / co-founders

**What to draft.**
1. `social.publish` plan for platform "reddit", account_handle "r/<sub>":
   - Title: ≤300 chars, lead with the *outcome* not the product name
     ("Built a tool that scores cold-email replies — what did I miss?"
     beats "Introducing CoolThing").
   - Body: 3 paragraphs. Paragraph 1 = the problem the operator hit.
     Paragraph 2 = what they shipped + the live URL. Paragraph 3 = the
     SPECIFIC ask (feedback on X, beta testers, etc.).
2. `artifact.text` to `drafts/reddit/<sub>-rules-checklist.md`:
   - Karma threshold met? (yes/no — Reddit profile read by the operator)
   - Account age threshold met?
   - Sub rules forbid this post? (operator confirms)
   - Self-promo ratio respected this month?
   - Cross-posting allowed?

**Honest constraints.**
- NO sock-puppet upvoting. NO multi-account posting. Both are bannable
  and waste the launch.
- One link in the body, max. More = spam-shaped.
- Reply to every top-level comment in the first 4 hours. If the
  operator can't, queue a reminder in the dashboard and post when they
  can — engagement decides the post's reach.
- If the launch is paid, say so up front in paragraph 2. Hiding it
  works once and earns a permaban.
