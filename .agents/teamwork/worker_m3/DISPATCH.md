## 2026-11-04T17:53:04Z
You are worker_m3, assigned to implement Milestone 3: Same-Domain Sub-Procedure Granularity (R6).

Your working directory is:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m3

Read:
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1\handoff.md (specifically §4.2)
- c:\Users\gaura\Documents\nivaan\tests\test_scenes_1_to_3_regression.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Exclusive file write ownership:
- backend/data/refined/troubleshooting/troubleshooting_tax.jsonl
- backend/rag/retriever.py
- tests/test_rag_loader.py
- tests/test_build_vector_db.py

Tasks:
1. Append authentic record `itr_ais_feedback_manual_01` to `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl` matching the exact schema and text in `survey_1/handoff.md §4.2.A`:
   - id: "itr_ais_feedback_manual_01"
   - source_url: "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/ais"
   - title: "Income Tax Department User Guide on Submitting Feedback on Annual Information Statement (AIS)"
   - section: "Submitting Online Feedback for SFT and Tax Credit Discrepancies in AIS and TIS"
   - text: "Annual Information Statement (AIS) Feedback Submission Protocol: Taxpayers can review financial transactions reported by reporting entities (SFT filers, banks, stock depositories) and submit transaction-level feedback directly on the e-filing portal.\n\nDirect Resolution Steps:\n1. Log in to incometax.gov.in with PAN and password.\n2. Navigate to 'Services > Annual Information Statement (AIS)'. Click 'Proceed' to redirect to the AIS compliance portal.\n3. Open the 'AIS' tab and select the relevant Financial Year. The screen displays Part A (General Information) and Part B (TDS/TCS, SFT, Payment of Taxes, Demand/Refund, Other Information).\n4. Under Part B, select the transaction category (e.g., SFT-005 for dividends, SFT-006 for interest, or securities transactions).\n5. Click on the specific transaction displaying an incorrect value or duplicate entry. Click 'Feedback' on the right side of the screen.\n6. Select the applicable feedback option from the dropdown:\n   - 'Information is correct'\n   - 'Information is not fully correct' (specify correct amount)\n   - 'Information relates to other PAN/Year'\n   - 'Information is duplicate / already reported'\n   - 'Information is denied'\n7. Submit the feedback. The system generates an Acknowledgement Receipt.\n\nStatutory Effect & TIS Update: Upon feedback submission, the modified value is immediately reflected in the Taxpayer Information Summary (TIS) as the 'Derived Value' used for pre-filling ITR. AIS feedback is NOT a Section 139(9) defective return proceeding, does not require filing a rectified JSON schema under e-Proceedings, and does not have a 15-day defect memo deadline."
   - category: "tax"
   - last_verified: "2026-11-04"
   - status: "automated_verified"
   - quality_score: 1.0
   - source_confidence: "official"
   - verification_method: "official_circular_and_sop"
   - retrieval_tags: ["troubleshooting", "manual", "ais", "annual_information_statement", "tis", "ais_feedback", "sft_feedback", "taxpayer_information_summary", "income_tax"]
   - language: "en"

2. Rebuild the vector database:
   Run: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db`

3. Reconcile point counts in `tests/test_rag_loader.py` and `tests/test_build_vector_db.py`:
   - In `tests/test_rag_loader.py`: `records_seen` becomes 1416, `accepted_records` becomes 1368, `unique_documents` becomes 1355, `retained_source_references` becomes 1368, and `tax` category becomes 116.
   - In `tests/test_build_vector_db.py`: `total_documents` becomes 1388, `points` becomes 1388, `documents` becomes 1388, `tax` category becomes 116.

4. In `backend/rag/retriever.py`:
   - In `_EXACT_CODES`: Add `"ais feedback"`, `"annual information statement"`, `"tis"`, `"sft feedback"`, `"sft"`.
   - In `_SYMPTOM_CLUSTERS`:
     Add dedicated `ais_feedback` cluster:
     ```python
     {
         "name": "ais_feedback",
         "match": ("ais feedback", "feedback on ais", "annual information statement", "ais mismatch", "sft", "wrong transaction in ais", "tis", "taxpayer information summary"),
         "boost_terms": ("annual information statement (ais) feedback", "sft feedback", "information is not fully correct", "information is denied", "information is duplicate", "derived value", "tis"),
         "conflicts": ("139(9)", "defective return", "defective notice", "cpc 2.0 defect memo", "e-proceedings", "15 calendar days", "corrected schema", "section 139(9)"),
     },
     ```
     In `defective_return` cluster: add `"ais feedback"`, `"feedback on ais"`, `"annual information statement"`, `"sft feedback"` to `conflicts`.
   - Add bidirectional sub-procedure disambiguation penalty between Section 139(9) and AIS feedback in `RagRetriever.search()`:
     ```python
     is_139_query = bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", lowered_q))
     is_ais_query = bool(re.search(r"\b(?:ais\s+feedback|feedback\s+on\s+ais|annual\s+information\s+statement|ais\s+mismatch)\b", lowered_q))

     if is_139_query:
         if "ais feedback" in lowered_doc or "sft feedback" in lowered_doc:
             score -= 0.40
             signals["sub_procedure_mismatch_penalty"] = -0.40
     elif is_ais_query:
         if "139(9)" in lowered_doc or "defective return" in lowered_doc:
             score -= 0.40
             signals["sub_procedure_mismatch_penalty"] = -0.40
     ```

5. Run test verification with Python 3.12:
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r6 or test_tier2_ais or test_tier2_139" -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r2 or test_tier1_r5" -v`

6. Document your results in `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m3\handoff.md` and send a completion message back.
