# Prompt history

| File | Status | Evidence |
|---|---|---|
| `PR-01_answer_v1.0.txt` | Live (copy of `../PR-01_answer.txt`) | Smoke test 31 Oct: 5 of 5 tickets behaved as specified |
| `PR-01_answer_v1.1_not_adopted.txt` | Tested 31 Oct, not adopted | Added "answer only if a passage fixes this specific problem". `python -m evaluation.prompt_compare --baseline history/PR-01_answer_v1.0.txt` on dev tickets that could reach drafting: v1.0 and v1.1 both answered 12/12 "should answer" and 12/12 "not answerable". No measured effect, so v1.0 stays. |
| `PR-02_grounding_v1.0.txt` | Live (copy of `../PR-02_grounding.txt`) | Blocked a planted false sentence; passed clean drafts (31 Oct) |
| `PR-02_grounding_v1.1_not_adopted.txt` | Tested 31 Oct, not adopted (FR-13) | Added "does this ticket need a person anyway?". `python -m evaluation.review_compare --baseline history/PR-02_grounding_v1.0.txt` on 12+12 dev drafts: should-answer released 11 (v1.0) vs 8 (v1.1); not-answerable released 6 vs 4. Scaled to a real mix (14 good : 6 bad per 20 drafts), bad share of sent replies 19% vs 18%, with about a quarter fewer automated answers. No clear benefit, so v1.0 stays; `validate(prompt=...)` can switch v1.1 on. |
