# Eval - 2026-09-08 11:14 UTC

- model: `fake` (provider `fake`), prompt `v1`, embeddings `disabled`
- 20 documents x 15 questions = 300 cells, 60 model calls
- ingestion 17.0s, grid 30.2s

## Headline

| Metric | Value | Target | |
|---|---|---|---|
| Accuracy (all questions) | 71.0% | - | |
| Citation verification rate | 100.0% | >= 95% | PASS |
| Hallucination rate on "not present" | 73.3% | <= 2% | FAIL |
| "Not found" where an answer exists | 0.0% | - | |
| Failed cells | 0 | 0 | |
| Latency p50 / p95 (per model call) | 1 ms / 1 ms | - | |
| Cost per cell | $0.0001 | <= $0.02 | PASS |
| Cost per document | $0.0021 | - | |
| Tokens in / cached / out | 47,958 / 0 / 15,000 | - | |

## Per question

| Question | Type | Accuracy | Hallucinated / absent | Unverified | Failed |
|---|---|---|---|---|---|
| Governing law | text | 60.0% (12/20) | 0 / 0 | 0 | 0 |
| Initial term | text | 100.0% (20/20) | 0 / 4 | 0 | 0 |
| Termination for convenience | boolean | 60.0% (12/20) | 8 / 8 | 0 | 0 |
| Liability cap | text | 80.0% (16/20) | 4 / 4 | 0 | 0 |
| Indemnity | text | 100.0% (20/20) | 0 / 6 | 0 | 0 |
| Assignment | boolean | 20.0% (4/20) | 4 / 4 | 0 | 0 |
| Change of control | boolean | 40.0% (8/20) | 8 / 8 | 0 | 0 |
| Confidentiality term | text | 80.0% (16/20) | 4 / 4 | 0 | 0 |
| Non-compete | boolean | 40.0% (8/20) | 12 / 12 | 0 | 0 |
| Payment terms | text | 80.0% (16/20) | 4 / 4 | 0 | 0 |
| Auto-renewal | boolean | 60.0% (12/20) | 4 / 4 | 0 | 0 |
| Exclusivity | boolean | 80.0% (16/20) | 0 / 8 | 0 | 0 |
| IP ownership | text | 85.0% (17/20) | 3 / 4 | 0 | 0 |
| Data protection | boolean | 80.0% (16/20) | 4 / 5 | 0 | 0 |
| Dispute resolution | text | 100.0% (20/20) | 0 / 0 | 0 | 0 |

## Sample misses

- **Governing law**: golden_02.pdf: expected 'the State of New York', got 'Governing Law and Disputes 11.1 Any dispute arising out of this Agreement shall be finally resolved by arbitration under the LCIA Rules, seated in London.'
- **Governing law**: golden_04.pdf: expected 'Ireland', got 'Governing Law and Disputes 10.1 Any dispute as to sums payable shall be referred to an independent expert whose determination shall be final and binding;'
- **Governing law**: golden_07.pdf: expected 'the State of New York', got 'Governing Law and Disputes 11.1 Any dispute arising out of this Agreement shall be finally resolved by arbitration under the LCIA Rules, seated in London.'
- **Termination for convenience**: golden_03.pdf: answered 'Yes' where nothing exists
- **Termination for convenience**: golden_05.pdf: answered 'Yes' where nothing exists
- **Termination for convenience**: golden_08.pdf: answered 'Yes' where nothing exists
- **Liability cap**: golden_04.pdf: answered 'Services 2.1 Supplier shall provide the Services described in each Statement of Work with reasonable skill and care.' where nothing exists
- **Liability cap**: golden_09.pdf: answered 'Services 2.1 Supplier shall provide the Services described in each Statement of Work with reasonable skill and care.' where nothing exists
- **Liability cap**: golden_14.pdf: answered 'Services 2.1 Supplier shall provide the Services described in each Statement of Work with reasonable skill and care.' where nothing exists
- **Assignment**: golden_01.pdf: 
- **Assignment**: golden_03.pdf: answered 'Yes' where nothing exists
- **Assignment**: golden_04.pdf: 
- **Change of control**: golden_02.pdf: answered 'Yes' where nothing exists
- **Change of control**: golden_03.pdf: answered 'Yes' where nothing exists
- **Change of control**: golden_04.pdf: 
- **Confidentiality term**: golden_03.pdf: answered 'Term and Termination 3.1 This Agreement commences on the Effective Date and continues for an initial term of three (3) years (the "Initial Term").' where nothing exists
- **Confidentiality term**: golden_08.pdf: answered 'Term and Termination 3.1 This Agreement commences on the Effective Date and continues for an initial term of three (3) years (the "Initial Term").' where nothing exists
- **Confidentiality term**: golden_13.pdf: answered 'Term and Termination 3.1 This Agreement commences on the Effective Date and continues for an initial term of three (3) years (the "Initial Term").' where nothing exists
- **Non-compete**: golden_01.pdf: answered 'Yes' where nothing exists
- **Non-compete**: golden_03.pdf: answered 'Yes' where nothing exists
- **Non-compete**: golden_04.pdf: answered 'Yes' where nothing exists
- **Payment terms**: golden_05.pdf: answered 'SOFTWARE AS A SERVICE AGREEMENT This agreement (the "Agreement") is made between Threadneedle Estates Limited ("Customer") and Salter Row Consulting Limited ("Supplier").' where nothing exists
- **Payment terms**: golden_10.pdf: answered 'SOFTWARE AS A SERVICE AGREEMENT This agreement (the "Agreement") is made between Threadneedle Estates Limited ("Customer") and Salter Row Consulting Limited ("Supplier").' where nothing exists
- **Payment terms**: golden_15.pdf: answered 'SOFTWARE AS A SERVICE AGREEMENT This agreement (the "Agreement") is made between Threadneedle Estates Limited ("Customer") and Salter Row Consulting Limited ("Supplier").' where nothing exists
- **Auto-renewal**: golden_02.pdf: 
- **Auto-renewal**: golden_05.pdf: answered 'Yes' where nothing exists
- **Auto-renewal**: golden_20.pdf: answered 'Yes' where nothing exists
- **Exclusivity**: golden_05.pdf: 
- **Exclusivity**: golden_20.pdf: 
- **Exclusivity**: golden_10.pdf: 

> The placeholder model produced these answers (no OPENAI_API_KEY). The numbers measure the harness and the verification path, not extraction quality.
