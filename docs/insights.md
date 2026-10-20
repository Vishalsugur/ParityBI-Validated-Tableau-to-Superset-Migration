# Insights for the service desk and the documentation team

Population: 24,644 incidents opened 29 Feb – 31 May 2016 at an IT company's service desk (real, anonymised ServiceNow data). Category and group names are anonymised by the source, so findings name "Category 26" rather than "Email". The method carries over directly to real labels.

## 1. Every handoff costs time

| Handoffs (reassignments) | Share of incidents | Median resolution | SLA met (from 16 Mar) |
|---|---|---|---|
| 0 | 54% | **0.7 h** | 87% |
| 1 | 25% | 42 h | 68% |
| 2 | 9% | 103 h | 49% |
| 3 or more | 11% | **192 h** | 33% |

Each additional handoff adds roughly two to four days to the median and lowers the chance of meeting SLA. This is a relationship, not proof of cause, since harder incidents get passed on more often. But it shows where the time goes, and it is the gap that first-line knowledge articles are meant to close: if the first agent can solve it, no handoff happens.

**For the documentation team:** knowledge articles for first-line agents have the biggest potential in categories with many handoffs.

## 2. Where to write knowledge articles first

Ranking categories by **incidents not solved at first contact**:

| Rank | Category | Incidents | Not solved at first contact | First-contact resolution |
|---|---|---|---|---|
| 1 | Category 26 | 3,338 | 1,601 | 52% |
| 2 | Category 53 | 2,678 | 1,269 | 53% |
| 3 | Category 42 | 3,516 | 1,210 | 66% |
| 4 | Category 46 | 2,432 | 1,083 | 55% |
| 5 | Category 23 | 1,063 | 925 | **13%** |

Category 23 stands out: only 13% solved at first contact, 1.75 handoffs on average. A focused set of articles or a first-line troubleshooting guide is likely the highest-value single piece of documentation here. Category 42 has many handoffs only because it is the largest; its first-contact rate is already above average. The live table is on the *Knowledge & Documentation Insights* dashboard.

## 3. Waiting for the user is a third of the open time

Before an incident is resolved, **30%** of all open hours are spent in *Awaiting User Info*. It affects 22% of incidents, with a median of 18 hours per wait.

Clearer intake forms ("please include your device, error message, screenshot") and self-help guides that ask for this information up front reduce this wait without any extra support staff.

## 4. The service desk stabilised during March

- Median resolution time per week fell from **91 h** (week of 29 Feb) to **1–5 h** from mid-April.
- The backlog of open incidents peaked at **2,119 on 21 Mar 2016** and then fell steadily.
- From April: median resolution 3.4 h, SLA met 77%, first-contact resolution 60%.

The first weeks look like a go-live or a backlog clean-up. Reports that average over the whole period understate how well the desk ran from April.

## 5. Two tracking changes, and why they matter

| Date | What changed | Evidence |
|---|---|---|
| **11 Mar 2016** | "Knowledge base document used" flag | 97.8% of incidents on 10 Mar, 1.5% on 11 Mar, ~1% afterwards |
| **16 Mar 2016** | SLA measurement | Incidents fixed in under 4 h: 35% "met SLA" before, 99% after, with unchanged resolution times |

Without noticing these, the data says that **using a knowledge article makes incidents slower** (77.6 h vs 10.9 h median) and **less likely to meet SLA** (27% vs 70%). Both results are artefacts: 97% of "knowledge used" incidents come from the first ten days, which were also the slowest and were measured under the old SLA logic.

**Recommendation:** fix knowledge-article tracking first (make linking an article consistent, or log article views per incident). Without it, the documentation team cannot measure the impact of its work. The pipeline's level-shift checks catch the next change like this automatically.

## 6. Other observations

- **Channel:** 99.9% of incidents came in by phone (36 by email, none self-service in this period). Self-service is untapped, which is relevant for any help center or knowledge base strategy.
- **Critical and High priority incidents almost never met SLA**, even after 16 March (1.8% and 0.6%), with medians of 72 h and 28 h. Either the targets are unrealistic or the SLA clock is configured wrong for these priorities. Worth asking before using SLA for staffing decisions.
- **Reopen rate is low (1.1%)** but rises with handoffs: 0.45% with no handoff vs 3.7% with three or more.
