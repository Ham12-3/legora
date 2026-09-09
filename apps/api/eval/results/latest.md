# Eval - 2026-09-08 16:40 UTC

- model: `gpt-5-mini` (provider `openai`), prompt `v2`, embeddings `openai`
- 20 documents x 15 questions = 300 cells, 60 model calls
- ingestion 42.0s, grid 1108.3s

## Headline

| Metric | Value | Target | |
|---|---|---|---|
| Accuracy (all questions) | 91.7% | - | |
| Citation verification rate | 100.0% | >= 95% | PASS |
| Hallucination rate on "not present" | 5.3% | <= 2% | FAIL |
| "Not found" where an answer exists | 0.0% | - | |
| Failed cells | 0 | 0 | |
| Latency p50 / p95 (per model call) | 16967 ms / 22844 ms | - | |
| Cost per cell | $0.0006 | <= $0.02 | PASS |
| Cost per document | $0.0091 | - | |
| Tokens in / cached / out | 92,955 / 0 / 79,518 | - | |

## Per question

| Question | Type | Accuracy | Hallucinated / absent | Unverified | Failed |
|---|---|---|---|---|---|
| Governing law | text | 100.0% (20/20) | 0 / 0 | 0 | 0 |
| Initial term | text | 100.0% (20/20) | 0 / 4 | 0 | 0 |
| Termination for convenience | boolean | 100.0% (20/20) | 0 / 8 | 0 | 0 |
| Liability cap | text | 100.0% (20/20) | 0 / 4 | 0 | 0 |
| Indemnity | text | 35.0% (7/20) | 0 / 6 | 0 | 0 |
| Assignment | boolean | 100.0% (20/20) | 0 / 4 | 0 | 0 |
| Change of control | boolean | 100.0% (20/20) | 0 / 8 | 0 | 0 |
| Confidentiality term | text | 100.0% (20/20) | 0 / 4 | 0 | 0 |
| Non-compete | boolean | 80.0% (16/20) | 4 / 12 | 0 | 0 |
| Payment terms | text | 100.0% (20/20) | 0 / 4 | 0 | 0 |
| Auto-renewal | boolean | 100.0% (20/20) | 0 / 4 | 0 | 0 |
| Exclusivity | boolean | 100.0% (20/20) | 0 / 8 | 0 | 0 |
| IP ownership | text | 60.0% (12/20) | 0 / 4 | 0 | 0 |
| Data protection | boolean | 100.0% (20/20) | 0 / 5 | 0 | 0 |
| Dispute resolution | text | 100.0% (20/20) | 0 / 0 | 0 | 0 |

## Sample misses

- **Indemnity**: golden_01.pdf: expected 'Supplier shall indemnify Customer', got "Supplier indemnifies Customer against all losses arising from any claim that the Services infringe a third party's intellectual property rights."
- **Indemnity**: golden_02.pdf: expected 'Supplier shall indemnify Customer', got "Supplier indemnifies Customer against all losses arising from any claim that the Services infringe a third party's intellectual property rights."
- **Indemnity**: golden_05.pdf: expected 'Supplier shall indemnify Customer', got "Supplier indemnifies Customer against all losses arising from any claim that the Services infringe a third party's intellectual property rights."
- **Non-compete**: golden_04.pdf: answered 'Yes' where nothing exists
- **Non-compete**: golden_09.pdf: answered 'Yes' where nothing exists
- **Non-compete**: golden_13.pdf: answered 'Yes' where nothing exists
- **IP ownership**: golden_01.pdf: expected 'vest in Customer', got 'The Customer owns the intellectual property in the deliverables.'
- **IP ownership**: golden_04.pdf: expected 'vest in Customer', got 'Customer.'
- **IP ownership**: golden_09.pdf: expected 'vest in Customer', got 'Customer'
