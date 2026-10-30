# Region and arrival-time analysis notes

AI-assisted analysis, kept for later use (fairness audit, report). Not used in the Stage 1 workbook:
the regional gap had no explanation strong enough to record as a finding.
Tables: `evidence.md` E7 (outcomes), E16 (ticket mix), E17 (like-for-like), E18 (fluency), E19 (arrival time).

## What was ruled out

| Possible explanation | Evidence | Result |
|---|---|---|
| Language fluency | Every region is 75–79% fluent (E16) | Does not explain it |
| Plan mix | North America's plan mix is close to average (E16) | Does not explain it |
| Time zone | Latin America shares North America's time zones but sits at the opposite end of E7 | Does not explain it |
| Arrival time | Region shares are similar in every arrival band (E19) | Does not explain it |
| Harder tickets | Asia-Pacific: yes (fewest answerable, most must-escalate, E16). Latin America: no (fewest must-escalate) | Explains Asia-Pacific only |

## What remains

- **Latin America** still does worst on like-for-like tickets (E17): 42% escalated vs 25% in North America,
  satisfaction 2.75 vs 3.15–3.21 elsewhere, 22% repeat contacts. The difference is in how these customers
  are served, not in what they ask. The data cannot say why.
- **Asia-Pacific** matches Europe like-for-like (E17); its overall gap comes from harder tickets.
- **Sofia's non-fluent claim** holds in Asia-Pacific only: satisfaction 2.68 non-fluent vs 3.01 fluent
  (E18). Across all regions it averages out (E6).

## Arrival time (separate finding)

- Tickets arriving 20:00–04:00 UTC resolve in about 55 min (median); 04:00–20:00 UTC take 250–350 min (E19).
- Weekend tickets: median 266 min vs 198 weekday, and 27% vs 20% repeat contacts (E19).
- The interviews never mention support hours; Ravi expects no reply until the next day if he writes at 4pm.
- The data does not say when the team works, so describe this as a pattern, not a schedule.

## Caveats

- Small samples: Latin America has 60 tickets (40 like-for-like, 15 non-fluent); Asia-Pacific has 25 non-fluent.
- No significance tests run. Treat these as patterns to test, not proven differences.
- Region by plan was not analysed: Latin America has only 4 enterprise tickets.

## Where this may be used

- Fairness audit (Governance Framework): segment by region as well as tier and fluency; Latin America is the
  group to watch.
- Report: as an example of an explanation tested and ruled out.
