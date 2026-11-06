# Task Assignment: Survey 2 - EPFO Corpus, Manifest, and CRAG Scraper Pipeline

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
4. Write your complete findings to `.agents/teamwork/survey_2/handoff.md`.
