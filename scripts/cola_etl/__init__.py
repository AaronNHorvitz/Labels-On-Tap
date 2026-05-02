"""Local ETL helpers for public COLA registry research.

The ETL package is intentionally separate from the FastAPI runtime. It fetches
and parses public registry artifacts into a local, gitignored workspace so the
app can later consume curated fixtures instead of scraping TTB during demos.
"""
