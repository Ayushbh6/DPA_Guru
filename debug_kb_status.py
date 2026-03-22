import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres")

# Convert standard postgresql+psycopg URL to postgresql:// for simple sqlalchemy test if needed
# but SQLAlchemy should handle postgresql+psycopg fine if installed.
try:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        print("--- Database Connection Successful ---")
        
        # Check kb_sources
        sources_count = conn.execute(text("SELECT count(*) FROM kb_sources")).scalar()
        print(f"Total kb_sources: {sources_count}")
        
        # Check kb_chunks
        chunks_count = conn.execute(text("SELECT count(*) FROM kb_chunks")).scalar()
        print(f"Total kb_chunks: {chunks_count}")
        
        # Check if embeddings are populated
        if chunks_count > 0:
            null_embeddings = conn.execute(text("SELECT count(*) FROM kb_chunks WHERE embedding IS NULL")).scalar()
            print(f"Chunks with NULL embeddings: {null_embeddings}")
            
            # Check structure extraction (structured_json)
            sample = conn.execute(text("SELECT structured_json, embedding IS NOT NULL as has_embedding FROM kb_chunks LIMIT 1")).fetchone()
            if sample:
                import json
                structured_data = sample[0]
                short_desc = structured_data.get('short_description', 'N/A')
                print(f"Sample short_description (from json): {short_desc[:50]}...")
                print(f"Sample has_embedding: {sample[1]}")
        
        # Check kb_ingest_runs
        runs = conn.execute(text("SELECT id, status, completed_at FROM kb_ingest_runs ORDER BY created_at DESC LIMIT 5")).fetchall()
        print("\n--- Recent Ingest Runs ---")
        for r in runs:
            print(f"ID: {r[0]}, Status: {r[1]}, Completed: {r[2]}")

except Exception as e:
    print(f"Error connecting to database: {e}")
