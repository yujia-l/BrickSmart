"""Google Cloud Storage helpers for the ksrag AI RAG backend (the GCP equivalent of the old boto3/S3
utilities). This is the ONE place that imports the optional google-cloud-storage SDK, so:
  * modules don't each import it (no duplication), and
  * a missing dependency raises a clear, actionable message instead of a bare ModuleNotFoundError.

Auth is via Application Default Credentials - NOT hard-coded keys:
    set GOOGLE_APPLICATION_CREDENTIALS=<service-account.json>   or   gcloud auth application-default login
Optional project via the GCP_PROJECT_ID env var (or pass project=...).

The SDK is imported lazily inside get_client(), so `import ksrag` never requires it — only the GCS code
paths do.
"""
import os
from pathlib import Path
from app.core.logging import get_logger
from dotenv import load_dotenv

load_dotenv()  # load .env if present, so GCP_PROJECT_ID can be set there

_log = get_logger("gcs")
_CLIENT = None


def get_client(project=None):
    """Return a cached, authenticated google.cloud.storage.Client, or raise a helpful error."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    try:
        from google.cloud import storage
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "google-cloud-storage is not installed (needed for GCS access).\n"
            "  Install it:   pip install google-cloud-storage\n"
            "  Authenticate: set GOOGLE_APPLICATION_CREDENTIALS=<service-account.json>\n"
            "                or run  gcloud auth application-default login"
        ) from e
    _CLIENT = storage.Client(project=project or os.getenv("GCP_PROJECT_ID"))
    return _CLIENT


def get_bucket(bucket, project=None):
    """Return a bucket handle."""
    return get_client(project).bucket(bucket)


def _object_name(gcs_folder, name):
    return f"{gcs_folder.strip('/')}/{name}" if gcs_folder else name


# ─────────────────────────── upload ───────────────────────────
def upload_file(bucket, gcs_folder, file_path, object_name=None):
    """Upload a local file to gs://<bucket>/<gcs_folder>/<file>. Returns True on success."""
    object_name = object_name or _object_name(gcs_folder, Path(file_path).name)
    try:
        get_bucket(bucket).blob(object_name).upload_from_filename(str(file_path))
        _log.info("uploaded %s -> gs://%s/%s", file_path, bucket, object_name)
        return True
    except Exception as e:
        _log.error("upload failed (%s -> gs://%s/%s): %s", file_path, bucket, object_name, e)
        return False


def upload_bytes(bucket, object_name, data, content_type="application/octet-stream"):
    """Upload in-memory bytes/str to gs://<bucket>/<object_name>. Returns True on success."""
    try:
        get_bucket(bucket).blob(object_name).upload_from_string(data, content_type=content_type)
        _log.info("uploaded bytes -> gs://%s/%s", bucket, object_name)
        return True
    except Exception as e:
        _log.error("upload_bytes failed (gs://%s/%s): %s", bucket, object_name, e)
        return False


# ─────────────────────────── download ───────────────────────────
def download_file(bucket, gcs_folder, filename, dest_path):
    """Download gs://<bucket>/<gcs_folder>/<filename> to dest_path. Returns True on success."""
    object_name = _object_name(gcs_folder, filename)
    try:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        get_bucket(bucket).blob(object_name).download_to_filename(str(dest_path))
        _log.info("downloaded gs://%s/%s -> %s", bucket, object_name, dest_path)
        return True
    except Exception as e:
        _log.error("download failed (gs://%s/%s): %s", bucket, object_name, e)
        return False


def download_file_to_local_folder(bucket, gcs_folder, filename, local_folder):
    """Download an object into local_folder/, keeping its filename. Returns the local path or None."""
    dest = Path(local_folder) / filename
    return str(dest) if download_file(bucket, gcs_folder, filename, dest) else None


def download_and_extract_zip(bucket, gcs_folder, zip_object_name, local_folder):
    """Download a .zip object and extract it into local_folder/. Returns local_folder or None."""
    import zipfile, tempfile
    local_folder = Path(local_folder)
    local_folder.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp()) / Path(zip_object_name).name
    if not download_file(bucket, gcs_folder, zip_object_name, tmp):
        return None
    try:
        with zipfile.ZipFile(tmp) as zf:
            zf.extractall(local_folder)
        _log.info("extracted %s -> %s", zip_object_name, local_folder)
        return str(local_folder)
    except Exception as e:
        _log.error("unzip failed (%s): %s", zip_object_name, e)
        return None
    finally:
        try: tmp.unlink()
        except Exception: pass


# ─────────────────────────── listing / existence ───────────────────────────
def list_files(bucket, prefix=""):
    """List object names under gs://<bucket>/<prefix>."""
    try:
        return [b.name for b in get_client().list_blobs(bucket, prefix=prefix)]
    except Exception as e:
        _log.error("list failed (gs://%s/%s): %s", bucket, prefix, e)
        return []


def blob_exists(bucket, object_name):
    """True if gs://<bucket>/<object_name> exists."""
    try:
        return get_bucket(bucket).blob(object_name).exists()
    except Exception as e:
        _log.error("exists check failed (gs://%s/%s): %s", bucket, object_name, e)
        return False


# backwards-compat alias used by datasource.py / knowledge.py
def bucket(name):
    return get_bucket(name)
