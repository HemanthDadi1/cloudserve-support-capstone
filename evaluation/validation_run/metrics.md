# Metrics report

Input: `data/validation_tickets.json`

## Volume

| Measure | Value |
|---|---|
| processed | 80 |
| auto answered | 13 |
| escalated | 67 |
| blocked | 5 |
| errors | 0 |

## Business

| Measure | Value |
|---|---|
| First contact resolution | 16.2% |
| Escalation rate | 83.8% |
| Time to first reply, automated answers (mean / median s) | 20.69 / 3.03 |
| Processing time, all tickets (mean / median / p95 s) | 4.43 / 0.04 / 62.06 |
| Labelled as answerable without a person | 60.0% |

## Technical

| Measure | Value |
|---|---|
| Intent accuracy / macro precision / macro recall | 100.0% / 100.0% / 100.0% |
| Intent calibration error | 0.003 |
| Urgency accuracy | 42.5% |
| Retrieval hit rate (expected article retrieved) | 96.2% |
| Citation accuracy (sent replies) | 78.7% |
| Sent but labelled escalate / must-not-auto | 2 / 0 |
| Routing agreement with labels | 51.2% |
| Unsupported sentences in drafts (before guardrails) | 4.4% |
| Unsupported sentences in sent replies | 0.0% |
| Latency median / p95 (s) | 0.04 / 62.06 |
| Models used for drafts | {'groq:qwen/qwen3.8-27b': 10, 'groq:openai/gpt-oss-120b': 7, 'groq:openai/gpt-oss-20b': 1} |

### Intent precision and recall per class

| Intent | Precision | Recall | Support |
|---|---|---|---|
| account_access | 1.0 | 1.0 | 4 |
| api_key_issue | 1.0 | 1.0 | 6 |
| api_usage_question | 1.0 | 1.0 | 4 |
| authentication_failure | 1.0 | 1.0 | 3 |
| billing_query | 1.0 | 1.0 | 10 |
| compliance_request | 1.0 | 1.0 | 1 |
| configuration_help | 1.0 | 1.0 | 3 |
| data_export | 1.0 | 1.0 | 1 |
| data_residency | 1.0 | 1.0 | 6 |
| database_issue | 1.0 | 1.0 | 1 |
| deployment_failure | 1.0 | 1.0 | 5 |
| feature_request | 1.0 | 1.0 | 3 |
| integration_help | 1.0 | 1.0 | 3 |
| onboarding | 1.0 | 1.0 | 4 |
| performance_degradation | 1.0 | 1.0 | 3 |
| quota_or_overage | 1.0 | 1.0 | 2 |
| rate_limit | 1.0 | 1.0 | 1 |
| rollback_request | 1.0 | 1.0 | 6 |
| security_incident | 1.0 | 1.0 | 4 |
| sso_configuration | 1.0 | 1.0 | 1 |
| unclear_request | 1.0 | 1.0 | 6 |
| webhook_issue | 1.0 | 1.0 | 3 |

## Governance

| Measure | Value |
|---|---|
| Decisions logged | 98 |
| Tickets with a routing decision | 80 |
| Log reconciles with tickets processed | True |
| Guardrail activations (instruction / pii / commitments / grounding / relevance) | 0 / 0 / 0 / 5 / 0 |
| Private data detections / in sent replies | 0 / 0 |
| Blocked reasons | {'grounding could not be checked': 2, 'a sentence is not supported by its sources': 3} |

## Fairness (share answered automatically)

**customer_tier** (largest gap between groups of 10+: 10.5 points)

| Group | Tickets | Answered automatically |
|---|---|---|
| business | 30 | 20.0% |
| enterprise | 8 | 37.5% |
| standard | 42 | 9.5% |

**customer_region** (largest gap between groups of 10+: 7.9 points)

| Group | Tickets | Answered automatically |
|---|---|---|
| asia_pacific | 21 | 14.3% |
| europe | 25 | 16.0% |
| latin_america | 7 | 0.0% |
| north_america | 27 | 22.2% |

**language_fluency** (largest gap between groups of 10+: 0.6 points)

| Group | Tickets | Answered automatically |
|---|---|---|
| fluent | 61 | 16.4% |
| non_fluent | 19 | 15.8% |
