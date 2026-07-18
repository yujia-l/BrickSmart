"""GCS -> database ingestion (the Google-Cloud data path for retrieval).

Pulls the processed bundles from ``gs://<GCS_PROCESSED_BUCKET>/<KNOWLEDGE_PREFIX>/`` and loads EACH
bundle into the Postgres + pgvector star schema (document_bundle + pdf_node w/ embeddings + rules),
so everything the /retrieve endpoint searches originates from Google Cloud Storage.

Run:
    python -m app.services.ingest                 # load all bundles from GCS (embeds with OpenAI)
    python -m app.services.ingest --no-embed      # load rows without embeddings (schema smoke test)
    python -m app.services.ingest --keep DIR      # keep the downloaded mirror in DIR (else a temp dir)
"""
import os
import tempfile

from app.core.config import settings
from app.core.logging import get_logger
from app.utils import gcs
from app.services import repository
from app.api.models.model_init import DBUtil

_log = get_logger("ingest")


def download_knowledge_from_gcs(settings=settings, dest=None):
    """Mirror the whole Knowledge_chunks/ tree from the processed GCS bucket into a local dir.

    Returns the local root that CONTAINS ``Knowledge_chunks/`` (what load_knowledge expects).
    """
    bucket = settings.GCS_PROCESSED_BUCKET or "kidspark-processed"
    prefix = settings.KNOWLEDGE_PREFIX
    root = dest or tempfile.mkdtemp(prefix="ksrag_gcs_")
    client = gcs.get_client()

    _log.info("downloading gs://%s/%s/ -> %s", bucket, prefix, root)
    n_files = 0
    for blob in client.list_blobs(bucket, prefix=f"{prefix}/"):
        if blob.name.endswith("/"):
            continue
        local_path = os.path.join(root, blob.name.replace("/", os.sep))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)
        n_files += 1
    _log.info("downloaded %d file(s) from gs://%s/%s/", n_files, bucket, prefix)
    if n_files == 0:
        raise RuntimeError(
            f"No objects under gs://{bucket}/{prefix}/ — run the processing pipeline to GCS first.")
    return root


def ingest_from_gcs(settings=settings, embed=True, dest=None, db=None):
    """Download the processed bundles from GCS and load each into the star schema. Returns bundle count."""
    root = download_knowledge_from_gcs(settings, dest=dest)
    db = db or DBUtil(settings)
    count = repository.load_knowledge(root, settings=settings, embed=embed, db=db)
    _log.info("ingestion complete: %d bundle(s) loaded from GCS into the database", count)
    return count


def _main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Load processed bundles from GCS into the Postgres + pgvector database.")
    parser.add_argument("--no-embed", action="store_true",
                        help="load rows WITHOUT OpenAI embeddings (schema/plumbing smoke test)")
    parser.add_argument("--keep", default="",
                        help="keep the downloaded GCS mirror in this dir (default: a temp dir)")
    args = parser.parse_args()

    embed = not args.no_embed
    if embed and not settings.OPENAI_API_KEY:
        _log.warning("OPENAI_API_KEY not set -> embeddings will be NULL (vector search returns nothing)")
    count = ingest_from_gcs(settings, embed=embed, dest=(args.keep or None))
    print(f"done: loaded {count} bundle(s) from "
          f"gs://{settings.GCS_PROCESSED_BUCKET or 'kidspark-processed'}/{settings.KNOWLEDGE_PREFIX}/ "
          f"into {settings.POSTGRESQL_DATABASE_URL.split('@')[-1]}")


if __name__ == "__main__":
    _main()
