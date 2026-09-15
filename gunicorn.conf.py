import multiprocessing

# ── Workers ───────────────────────────────────────────────────────────────────
# (2 × CPU cores) + 1 workers, each with 4 threads
# On 8 CPUs: 17 workers × 4 threads = 68 concurrent requests handled at once
workers      = (multiprocessing.cpu_count() * 2) + 1
worker_class = "gthread"   # threaded — better for I/O-bound Django + long AI calls
threads      = 4
worker_connections = 1000

# ── Binding ───────────────────────────────────────────────────────────────────
bind      = "0.0.0.0:8000"               # Docker: Nginx connects to web:8000
# bind    = "unix:/tmp/municipal_ai.sock" # use this for bare-metal (no Docker)

# ── Timeouts ──────────────────────────────────────────────────────────────────
timeout          = 120  # AI streaming calls can take 30-60s; give headroom
keepalive        = 5
graceful_timeout = 30   # finish in-flight requests before restart

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog  = "-"         # stdout (captured by systemd / Docker)
errorlog   = "-"
loglevel   = "warning"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ── Performance ───────────────────────────────────────────────────────────────
preload_app         = True   # load Django once in master process, fork to workers
max_requests        = 1000   # recycle workers to prevent memory leaks
max_requests_jitter = 100    # stagger restarts to avoid thundering herd

# ── Security ──────────────────────────────────────────────────────────────────
limit_request_line   = 4096
limit_request_fields = 100
forwarded_allow_ips  = "*"   # trust X-Forwarded-For from Nginx
