# GovBank Assistant: RAG Execution Plan

## How to execute it

RAG has two stages. You prepare the knowledge once, then run the query stage every time a user asks something.

### Stage A: Prepare the knowledge (done before users arrive)

**Step 1. Collect official sources.** Save the pages or PDFs with their URLs and dates in `data/raw/`.

**Step 2. Write or extract entries.** Turn each source into an entry in your own words (title, documents, steps, fees, source, date). Mark it unverified.

**Step 3. Verify.** A second person checks every fact against the official page, then sets `status: verified` and adds `last_verified`.

**Step 4. Store** the verified entries in `knowledge_base.json`.

**Step 5. Make them searchable.**
- *Version 1:* keyword and fuzzy matching over each entry's title and keywords. No index needed.
- *Version 2 (later):* split text into chunks, turn them into embeddings, and save them in `vector_index/`.

---

### Stage B: Answer each question (runs on every request)

**Step 6. Receive and clean the input.** The question comes in through `main.py`. If a document was uploaded, `ocr.py` reads it, and `guardrails.py` masks sensitive numbers before anything goes to an outside AI.

**Step 7. Retrieve.** `retrieval.py` searches the knowledge base and returns the best 1 or 2 matching entries, with a match score.

**Step 8. Check the match.** If the score is below your threshold, stop and return the safe answer: "I don't have a verified guide for this yet. Please check the official portal," with a link if you have one.

**Step 9. Build the prompt.** `explainer.py` puts together:
1. the instruction ("answer only from the context below; don't invent fees, dates, or steps; if it's missing, say so; don't tell the user what to decide")
2. the retrieved entry as the context
3. the user's question

**Step 10. Generate.** Send the prompt to the AI provider and ask for the answer in your fixed format (summary, documents needed, steps, warnings).

**Step 11. Validate and attach facts in code.** Check that the output matches the Answer shape. Then set `source_url` and `last_verified` from the entry itself, not from the AI's text, and add the disclaimer.

**Step 12. Show it.** The website displays the checklist, warnings, source, date, and disclaimer.

> **Workflow:** question → mask → retrieve → check match → prompt (context + rules) → AI → validate + attach source/date → show

---

### What a minimal version looks like in code

```python
def answer(question):
    entry, score = retrieve(question)            # Step 7
    if entry is None or score < 0.6:             # Step 8
        return not_found_answer()
    
    prompt = f"""Answer ONLY from the context. If the context lacks it, say so.
Do not invent fees, dates, or steps. Do not tell the user what to decide.

CONTEXT:
{entry}

QUESTION: {question}"""
    
    result = call_ai(prompt)                     # Steps 9-10 (the only API call)
    result["source_url"] = entry["source_url"]   # Step 11
    result["last_verified"] = entry["last_verified"]
    return result
```

---

### Build order

1. Stage A with 3 to 10 hand-verified entries (Steps 1 to 4).
2. Keyword retrieval and the not-found check (Steps 7 and 8), tested with 20 questions and no AI yet.
3. Add the AI call, prompt, and validation (Steps 9 to 11).
4. Connect the website (Step 12).
5. Only then add vector search, automated crawling, and the agent loop.

---

### How to know each step works

- **After Steps 1 to 4:** every entry has a source URL, a date, and a verified status.
- **After Steps 7 and 8:** 10 different phrasings find the right entry, and nonsense questions return not-found.
- **After Steps 9 to 11:** answers contain nothing that isn't in the entry, and source and date always appear.
