# Dispatch Task: worker_m3_gen2

- **Assigned Role**: teamwork_worker
- **Milestone**: Milestone 3 — Same-Domain Sub-Procedure Granularity (R6)
- **Objective**: Implement sub-procedure discrimination between Section 139(9) defective returns and AIS feedback.
- **Reference Files**:
  - `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
  - `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
  - `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1\handoff.md`

## 2026-11-04T18:07:05Z
You are worker_m3_gen2, assigned to implement Milestone 3: Same-Domain Sub-Procedure Granularity (R6).

Your working directory is:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m3_gen2

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
1. Append authentic record `itr_ais_feedback_manual_01` to `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl` matching the exact schema and text in `survey_1/handoff.md §4.2.A`.
2. Rebuild the vector database:
   Run: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db`
3. Reconcile point counts in `tests/test_rag_loader.py` and `tests/test_build_vector_db.py`.
4. In `backend/rag/retriever.py`:
   - In `_EXACT_CODES`: Add `"ais feedback"`, `"annual information statement"`, `"tis"`, `"sft feedback"`, `"sft"`.
   - In `_SYMPTOM_CLUSTERS`: Add dedicated `ais_feedback` cluster and update `defective_return` conflicts.
   - Add bidirectional sub-procedure disambiguation penalty between Section 139(9) and AIS feedback in `RagRetriever.search()`.
5. Run test verification with Python 3.12.
6. Document results in `handoff.md` and send completion message.
