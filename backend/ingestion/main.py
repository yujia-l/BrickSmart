"""Root entrypoint shim so `uvicorn main:app` and `python main.py` still work.

The real application factory lives in app/main.py (create_app()).
"""
from app.main import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False, log_config=None)
