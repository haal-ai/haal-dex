"""Debug: test the exact SQLite BM25 query path."""
import sys, asyncio
sys.path.insert(0, ".")

from app.engine.sqlite_bm25_backend import SQLiteBM25Backend

db_path = r"C:\Users\ppaccaud\coderepos\haal-ai\haal-dex\backend\data\support_kb.db"

# Test 1: BM25F with column weights (what the personality uses)
print("=== Test 1: BM25F with weights ===")
backend = SQLiteBM25Backend(
    db_path=db_path,
    fts_table="support_articles",
    ranking_algorithm="bm25f",
    column_weights=[10.0, 1.0, 5.0, 3.0],
)
print(f"is_available: {backend.is_available()}")
results = asyncio.run(backend.query("password reset", top_k=5))
print(f"Results: {len(results)}")
for r in results:
    print(f"  score={r.score:.4f} frag={r.document_fragment[:80]}")

# Test 2: BM25 Okapi (default, no weights)
print("\n=== Test 2: BM25 Okapi ===")
backend2 = SQLiteBM25Backend(
    db_path=db_path,
    fts_table="support_articles",
    ranking_algorithm="bm25_okapi",
)
results2 = asyncio.run(backend2.query("password reset", top_k=5))
print(f"Results: {len(results2)}")
for r in results2:
    print(f"  score={r.score:.4f} frag={r.document_fragment[:80]}")

# Test 3: Raw SQL to verify data exists
print("\n=== Test 3: Raw SQL ===")
import sqlite3
conn = sqlite3.connect(db_path)
rows = conn.execute("SELECT title FROM support_articles LIMIT 5").fetchall()
print(f"Articles in DB: {len(rows)}")
for row in rows:
    print(f"  {row[0]}")

# Test 4: Raw FTS5 MATCH
print("\n=== Test 4: Raw FTS5 MATCH ===")
rows = conn.execute(
    'SELECT title, -bm25(support_articles, 10.0, 1.0, 5.0, 3.0) AS rank '
    'FROM support_articles WHERE support_articles MATCH ? ORDER BY rank DESC LIMIT 3',
    ('password',)
).fetchall()
print(f"Raw MATCH results: {len(rows)}")
for title, rank in rows:
    print(f"  {rank:.4f} - {title}")

# Test 5: Sanitized query (what the backend does)
print("\n=== Test 5: Sanitized query ===")
sanitized = backend._sanitize_query("password reset")
print(f"Sanitized: {sanitized}")
rows = conn.execute(
    f'SELECT title, -bm25(support_articles, 10.0, 1.0, 5.0, 3.0) AS rank '
    f'FROM support_articles WHERE support_articles MATCH ? ORDER BY rank DESC LIMIT 3',
    (sanitized,)
).fetchall()
print(f"Sanitized MATCH results: {len(rows)}")
for title, rank in rows:
    print(f"  {rank:.4f} - {title}")

conn.close()
