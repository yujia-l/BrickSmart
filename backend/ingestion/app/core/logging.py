"""log_util — centralized, colorized, real-time logging for the ksrag AI RAG backend.

Every module logs under the `ksrag` logger namespace, so this single configuration captures ALL logs
for the solution. Console output is colorized (colorama) and flushed per record (real-time); optionally
every line is also written to a file (plain text, no color codes).

    from ksrag.log_util import get_logger
    log = get_logger(__name__)
    log.info("processing %s", bundle)

Environment:
    KSRAG_LOG_LEVEL   DEBUG | INFO | WARNING | ERROR | CRITICAL   (default: INFO)
    KSRAG_LOG_FILE    optional path — also capture all logs to this file
"""
import logging, os, sys, time
from contextlib import contextmanager

# colorama is optional — fall back to no color if it isn't installed
try:
    from colorama import init as _color_init, Fore, Style
    _color_init(autoreset=True)
except Exception:                       # pragma: no cover
    class _NoColor:
        def __getattr__(self, _): return ""
    Fore = Style = _NoColor()

_ROOT = "app"
_FMT = "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s"
_DATEFMT = "%H:%M:%S"
_CONFIGURED = False


class CustomFormatter(logging.Formatter):
    """Logging formatter that adds level-based colors (from the project spec)."""
    grey = Style.DIM + Fore.WHITE
    green = Fore.GREEN
    yellow = Fore.YELLOW
    red = Fore.RED

    FORMATS = {
        logging.DEBUG:    grey + _FMT,
        logging.INFO:     green + _FMT,
        logging.WARNING:  yellow + _FMT,
        logging.ERROR:    red + _FMT,
        logging.CRITICAL: red + _FMT,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, _FMT)
        return logging.Formatter(log_fmt, datefmt=_DATEFMT, style="%").format(record)


class _FlushingHandler(logging.StreamHandler):
    """StreamHandler that flushes after every record -> logs appear in real time."""
    def emit(self, record):
        super().emit(record)
        self.flush()


def configure(level=None, logfile=None, force=False):
    """Configure logging once (idempotent) so EVERY log in the process is visible in real time.

    The colorized, per-record-flushed handler is attached to the **root** logger, so it captures not
    just ``ksrag.*`` but also third-party libraries (docling, openai, sqlalchemy, google, uvicorn, …).
    The ``ksrag`` namespace keeps its own level but has no handler of its own, so it propagates to the
    single root handler (no double printing).
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    level = (level or os.getenv("KSRAG_LOG_LEVEL", "INFO")).upper()
    logfile = logfile if logfile is not None else os.getenv("KSRAG_LOG_FILE")

    root = logging.getLogger()                    # ROOT logger -> capture ALL logs across the project
    root.setLevel(level)
    for handler in list(root.handlers):           # replace any pre-existing handlers with ours
        root.removeHandler(handler)

    console = _FlushingHandler(sys.stdout)
    console.setFormatter(CustomFormatter())       # colorized
    root.addHandler(console)

    if logfile:                                   # capture-all to file too (plain, no color codes)
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
        root.addHandler(fh)

    # Re-enable any logger a prior/hostile config muted (e.g. dictConfig(disable_existing_loggers=True)
    # from uvicorn/gunicorn). Without this, ksrag.* loggers created at import time could stay disabled
    # and their output would silently vanish. We only flip `disabled` — never `propagate` — so libraries
    # with their own handlers (uvicorn.access, …) don't start double-printing.
    for _lgr in logging.Logger.manager.loggerDict.values():
        if isinstance(_lgr, logging.Logger):
            _lgr.disabled = False

    # ksrag namespace: own level, but no own handler -> propagates to the root handler above.
    ks = logging.getLogger(_ROOT)
    ks.handlers.clear()
    ks.propagate = True
    ks.setLevel(level)

    # Keep very chatty dependencies readable so real-time output stays useful.
    for noisy, noisy_level in (("pdfminer", logging.ERROR), ("urllib3", logging.WARNING),
                               ("httpx", logging.WARNING), ("httpcore", logging.WARNING),
                               ("openai", logging.WARNING), ("PIL", logging.WARNING),
                               ("sqlalchemy.engine", logging.WARNING)):
        logging.getLogger(noisy).setLevel(noisy_level)
    _CONFIGURED = True


def get_logger(name=_ROOT):
    """Return a child logger under the `ksrag` namespace (auto-configures on first use)."""
    configure()
    if not name.startswith(_ROOT):
        name = f"{_ROOT}." + name.replace(_ROOT + ".", "")
    return logging.getLogger(name)


def setup_logger(name=_ROOT):
    """Alias matching the requested API — a colorized, real-time logger for `name`."""
    return get_logger(name)


def set_level(level):
    """Change the log level at runtime, e.g. set_level('DEBUG'). Applies to root + ksrag."""
    configure()
    lvl = str(level).upper()
    logging.getLogger().setLevel(lvl)
    logging.getLogger(_ROOT).setLevel(lvl)


@contextmanager
def timed(logger, message):
    """Log start + elapsed time:  with timed(log, 'ingest'): ..."""
    logger.info("%s ...", message)
    t0 = time.time()
    try:
        yield
    finally:
        logger.info("%s - done in %.2fs", message, time.time() - t0)


__all__ = ["configure", "get_logger", "setup_logger", "set_level", "timed", "CustomFormatter"]
