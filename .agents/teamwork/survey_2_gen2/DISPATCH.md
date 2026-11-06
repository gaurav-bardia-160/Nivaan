# Task Assignment: Survey 2 (Gen 2) - EPFO Corpus, Manifest, and CRAG Scraper Pipeline

## Mission
Investigate the EPFO corpus documents, manifest, ingestion pipeline, and CRAG scraper to prepare for R1 and R5.

## Scope & Questions
1. Read `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`.
2. Inspect `backend/data/rag_manifest.json`:
   - Locate the 3 EPFO documents hosted on `pmvbry-cdn.epfindia.gov.in`:
     * Joint Declaration SOP
     * Attestation Framework for Closed Establishments
     * Passbook/Cheque Validation Standards
   - Check where these files are stored locally or how they are ingested/indexed.
   - Verify their actual content: does it match their titles, or is it PMVBRY boilerplate?
   - Identify the source/URLs or local official circulars/SOPs needed for authentic content.
   - Trace how the corpus vector index is built or updated from this manifest.
3. Inspect the Corrective RAG (CRAG) fallback path:
   - Where is live web search / scraping implemented?
   - Where are `requests` and `BeautifulSoup` currently used?
   - How can `trafilatura` be introduced to cleanly extract content and eliminate DOM noise?
   - Check dependencies: is `trafilatura` installed or listed in requirements/pyproject?
4. Write your complete findings to `.agents/teamwork/survey_2_gen2/handoff.md`.


## 2026-11-04T13:12:44Z
Sender: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
Content:
You are survey_2_gen2, an exploration agent (teamwork_explorer).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_2_gen2
Original Request path: c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md

Read c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md and c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_2_gen2\DISPATCH.md.
Investigate the EPFO corpus documents, manifest, ingestion pipeline, and CRAG scraper to prepare for R1 and R5.
1. Inspect `backend/data/rag_manifest.json` and examine the 3 EPFO documents hosted on `pmvbry-cdn.epfindia.gov.in`:
   - Joint Declaration SOP
   - Attestation Framework for Closed Establishments
   - Passbook/Cheque Validation Standards
2. Inspect the local storage/corpus files for these documents. Verify whether their content matches their titles or consists of PMVBRY boilerplate.
3. Check where authentic official EPFO circulars/SOPs can be obtained or are present in the repo/system, and how to ingest them.
4. Inspect the Corrective RAG (CRAG) fallback path: locate where live web search / requests / BeautifulSoup are used, how `trafilatura` can be integrated to eliminate DOM noise, and check dependencies.
5. Create your progress.md and update it as you go.
Write your complete analysis and structured handoff to:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_2_gen2\handoff.md
When finished, notify me using send_message.
