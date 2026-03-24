"""
gunicorn.conf.py — KrisLynx LLP HR Portal
Production Gunicorn configuration for Render.com
"""
import os
import multiprocessing

# ── Binding ────────────────────────────────────────────────────────────────────
port = os.getenv("PORT", "10000")
bind = f"0.0.0.0:{port}"

# ── Workers ────────────────────────────────────────────────────────────────────
# Render free tier: 512 MB RAM → keep workers low
# Formula: (2 × CPU cores) + 1, but cap at 4 for free tier
workers     = min(multiprocessing.cpu_count() * 2 + 1, 4)
threads     = 2          # threads per worker (good for I/O-heavy Firebase calls)
worker_class = "sync"    # sync is fine; switch to "gthread" for higher concurrency

# ── Timeouts ───────────────────────────────────────────────────────────────────
timeout           = 120   # Firestore cold starts can be slow on free tier
keepalive         = 5
graceful_timeout  = 30

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog    = "-"     # stdout  → Render captures this
errorlog     = "-"     # stderr
loglevel     = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ── Process naming ─────────────────────────────────────────────────────────────
proc_name = "krislynxllp-hr"

# ── Security ───────────────────────────────────────────────────────────────────
limit_request_line   = 4096
limit_request_fields = 100

# ── Lifecycle hooks ────────────────────────────────────────────────────────────
def on_starting(server):
    print(">  Gunicorn starting — KrisLynx HR Portal")

def post_fork(server, worker):
    """Re-initialize Firebase in each forked worker process."""
    import firebase_config
    try:
        firebase_config.init_firebase()
    except Exception as e:
        server.log.error(f"Firebase init failed in worker: {e}")

def worker_exit(server, worker):
    print(f"Worker {worker.pid} exited")
