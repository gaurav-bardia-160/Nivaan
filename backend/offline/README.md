# Offline knowledge pipeline

Planned order:

1. choose official sources in `backend/data/sources.json`
2. crawl approved pages with `crawl.py`
3. clean and chunk text with `clean_chunk.py`
4. create draft entries with `structure.py`
5. manually verify with `verify.py`
6. build searchable index with `build_index.py`

This folder is not meant for user uploads.
