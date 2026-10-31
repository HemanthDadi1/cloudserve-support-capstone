# Prompt history

| File | Status | Evidence |
|---|---|---|
| `PR-01_answer_v1.0.txt` | Live (copy of `../PR-01_answer.txt`) | Smoke test 31 Oct: 5 of 5 tickets behaved as specified |
| `PR-01_answer_v1.1_not_adopted.txt` | Tested 31 Oct, not adopted | Added "answer only if a passage fixes this specific problem". `python -m evaluation.prompt_compare --baseline history/PR-01_answer_v1.0.txt` on dev tickets that could reach drafting: v1.0 and v1.1 both answered 12/12 "should answer" and 12/12 "not answerable". No measured effect, so v1.0 stays. |
