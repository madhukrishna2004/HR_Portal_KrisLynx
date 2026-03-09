"""
KrisLynx LLP – HR Management Portal
app.py  |  Production build for Render
"""

import os, uuid, datetime, json, logging, time
from functools import wraps
from collections import defaultdict
from flask import Flask, render_template, request, jsonify, redirect, url_for, g
from firebase_config import (get_db, get_auth, get_bucket,
                              COLLECTIONS, CLIENT_CONFIG, init_firebase)
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════
#  STRUCTURED LOGGING
# ══════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("krislynx_hr")

# ══════════════════════════════════════════════════════════════════
#  APP FACTORY
# ══════════════════════════════════════════════════════════════════
app = Flask(__name__)
app.config["SECRET_KEY"]          = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["ENV"]                 = os.getenv("FLASK_ENV", "production")
app.config["DEBUG"]               = os.getenv("FLASK_ENV") == "development"
app.config["MAX_CONTENT_LENGTH"]  = 10 * 1024 * 1024   # 10 MB upload cap
app.config["JSON_SORT_KEYS"]      = False

IS_PROD = app.config["ENV"] == "production"

# ══════════════════════════════════════════════════════════════════
#  IN-PROCESS RATE LIMITER
#  (simple token-bucket per IP; good for single-instance Render free)
# ══════════════════════════════════════════════════════════════════
_rate_store: dict[str, list] = defaultdict(list)

def _rate_limit(max_calls: int, window_secs: int):
    """Decorator — limits an endpoint to max_calls per window_secs per IP."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            ip  = request.headers.get("X-Forwarded-For", request.remote_addr or "anon").split(",")[0].strip()
            now = time.monotonic()
            key = f"{fn.__name__}:{ip}"
            # Evict timestamps outside the window
            _rate_store[key] = [t for t in _rate_store[key] if now - t < window_secs]
            if len(_rate_store[key]) >= max_calls:
                return jsonify({"ok": False, "error": "Too many requests. Please slow down."}), 429
            _rate_store[key].append(now)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# ══════════════════════════════════════════════════════════════════
#  SECURITY HEADERS
# ══════════════════════════════════════════════════════════════════
@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"]           = "DENY"
    response.headers["X-Content-Type-Options"]    = "nosniff"
    response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"]          = "1; mode=block"
    response.headers["Permissions-Policy"]        = "camera=(), microphone=(), geolocation=()"
    if IS_PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# ── Request timing log ─────────────────────────────────────────────
@app.before_request
def start_timer():
    g.start = time.monotonic()

@app.after_request
def log_request(response):
    dur_ms = round((time.monotonic() - getattr(g, "start", time.monotonic())) * 1000, 1)
    if not request.path.startswith("/static"):
        logger.info(f'{request.method} {request.path} → {response.status_code} ({dur_ms}ms)')
    return response

# ── Template context ───────────────────────────────────────────────
@app.context_processor
def inject_globals():
    return {
        "firebase_config": json.dumps(CLIENT_CONFIG),
        "app_version":     os.getenv("RENDER_GIT_COMMIT", "dev")[:7],
    }

# ── Error handlers ─────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Endpoint not found"}), 404
    return render_template("error.html", code=404, message="Page not found"), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"ok": False, "error": "Method not allowed"}), 405

@app.errorhandler(429)
def too_many(e):
    return jsonify({"ok": False, "error": "Too many requests"}), 429

@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 error: {e}")
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Internal server error"}), 500
    return render_template("error.html", code=500, message="Something went wrong"), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({"ok": False, "error": "File too large (max 10 MB)"}), 413

# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════
def now_iso():   return datetime.datetime.utcnow().isoformat()
def today_str(): return datetime.datetime.utcnow().strftime("%Y-%m-%d")
def short_id(prefix=""): return prefix + str(uuid.uuid4())[:8].upper()

def log_activity(actor_id, actor_name, action, detail=""):
    try:
        get_db().collection(COLLECTIONS["activity_logs"]).add({
            "actor_id": actor_id, "actor_name": actor_name,
            "action": action, "detail": detail, "ts": now_iso(),
        })
    except Exception as ex:
        logger.warning(f"Activity log failed: {ex}")

def verify_token(id_token):
    try:
        return get_auth().verify_id_token(id_token)
    except Exception:
        return None

def ok(data=None, **extra):
    payload = {"ok": True}
    if isinstance(data, dict):  payload.update(data)
    elif isinstance(data, list): payload["items"] = data
    payload.update(extra)
    return jsonify(payload)

def err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

# ══════════════════════════════════════════════════════════════════
#  SYSTEM ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route("/health")
def health():
    """Render health-check endpoint."""
    try:
        # Lightweight DB ping
        get_db().collection(COLLECTIONS["users"]).limit(1).get()
        db_ok = True
    except Exception:
        db_ok = False
    status = "ok" if db_ok else "degraded"
    code   = 200  if db_ok else 503
    return jsonify({
        "status":  status,
        "service": "krislynxllp-hr-portal",
        "db":      "connected" if db_ok else "error",
        "version": os.getenv("RENDER_GIT_COMMIT", "dev")[:7],
    }), code

@app.route("/")
def index():
    return redirect(url_for("login_page"))

# ══════════════════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route("/login")
def login_page():
    firebase_config = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID"),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": os.getenv("FIREBASE_APP_ID"),
        "measurementId": os.getenv("FIREBASE_MEASUREMENT_ID"),
    }

    return render_template("login.html", firebase_config=firebase_config)
    
@app.route("/hr/dashboard")
def hr_dashboard():     return render_template("dashboard_hr.html")

@app.route("/hr/employees")
def hr_employees():     return render_template("employees.html")

@app.route("/hr/projects")
def hr_projects():      return render_template("projects.html")

@app.route("/hr/tasks")
def hr_tasks():         return render_template("tasks.html")

@app.route("/hr/eod")
def hr_eod():           return render_template("eod.html")

@app.route("/employee/dashboard")
def emp_dashboard():    return render_template("dashboard_employee.html")

@app.route("/employee/projects")
def emp_projects():     return render_template("projects.html")

@app.route("/employee/tasks")
def emp_tasks():        return render_template("tasks.html")

@app.route("/employee/eod")
def emp_eod():          return render_template("eod.html")

# ══════════════════════════════════════════════════════════════════
#  AUTH API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/auth/session", methods=["POST"])
@_rate_limit(30, 60)   # 30 login attempts per minute per IP
def auth_session():
    data     = request.get_json(silent=True) or {}
    id_token = data.get("idToken")
    if not id_token:
        return err("idToken required")

    decoded = verify_token(id_token)
    if not decoded:
        return err("Invalid or expired token", 401)

    uid = decoded["uid"]
    try:
        db  = get_db()
        doc = db.collection(COLLECTIONS["users"]).document(uid).get()
        if doc.exists:
            profile = doc.to_dict()
        else:
            profile = {
                "uid": uid, "email": decoded.get("email", ""),
                "name": decoded.get("name", decoded.get("email", "User")),
                "role": "employee", "status": "active",
                "employee_id": short_id("EMP"), "department": "",
                "join_date": today_str(), "created_at": now_iso(),
            }
            db.collection(COLLECTIONS["users"]).document(uid).set(profile)

        if profile.get("status") == "inactive":
            return err("This account has been deactivated. Contact HR.", 403)

        logger.info(f"Login: {uid} role={profile.get('role')}")
        return ok({"profile": profile, "role": profile.get("role", "employee")})
    except Exception as e:
        logger.error(f"auth_session error: {e}")
        return err("Authentication error", 500)


@app.route("/api/auth/create-employee", methods=["POST"])
@_rate_limit(10, 60)
def create_employee_account():
    data = request.get_json(silent=True) or {}
    for f in ["name", "email", "password"]:
        if not data.get(f):
            return err(f"Field '{f}' is required")
    if len(data["password"]) < 8:
        return err("Password must be at least 8 characters")
    try:
        user_record = get_auth().create_user(
            email=data["email"].lower().strip(),
            password=data["password"],
            display_name=data["name"].strip(),
        )
        emp_id  = short_id("EMP")
        profile = {
            "uid":          user_record.uid,
            "employee_id":  emp_id,
            "name":         data["name"].strip(),
            "email":        data["email"].lower().strip(),
            "department":   data.get("department", ""),
            "role":         data.get("role", "employee"),
            "position":     data.get("position", ""),
            "phone":        data.get("phone", ""),
            "join_date":    data.get("join_date", today_str()),
            "status":       "active",
            "profile_image": "",
            "created_at":   now_iso(),
        }
        get_db().collection(COLLECTIONS["users"]).document(user_record.uid).set(profile)
        log_activity("system", "HR Admin", "Created employee",
                     f"{data['name']} ({emp_id})")
        logger.info(f"Employee created: {emp_id} {data['email']}")
        return ok({"profile": profile})
    except Exception as e:
        logger.error(f"create_employee error: {e}")
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  EMPLOYEES API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/employees", methods=["GET"])
def list_employees():
    try:
        docs = get_db().collection(COLLECTIONS["users"]).stream()
        emps = sorted(
            [d.to_dict() for d in docs],
            key=lambda x: x.get("name", "").lower()
        )
        return ok({"employees": emps})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/employees/<uid>", methods=["GET"])
def get_employee(uid):
    try:
        doc = get_db().collection(COLLECTIONS["users"]).document(uid).get()
        if not doc.exists:
            return err("Employee not found", 404)
        return ok({"employee": doc.to_dict()})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/employees/<uid>", methods=["PUT"])
def update_employee(uid):
    data    = request.get_json(silent=True) or {}
    allowed = ["name", "department", "role", "position", "phone",
               "status", "profile_image"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return err("No valid fields to update")
    updates["updated_at"] = now_iso()
    try:
        get_db().collection(COLLECTIONS["users"]).document(uid).update(updates)
        log_activity("system", "HR Admin", "Updated employee", uid)
        return ok({"uid": uid})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/employees/<uid>/toggle", methods=["POST"])
def toggle_employee(uid):
    try:
        doc = get_db().collection(COLLECTIONS["users"]).document(uid).get()
        if not doc.exists:
            return err("Not found", 404)
        current    = doc.to_dict().get("status", "active")
        new_status = "inactive" if current == "active" else "active"
        get_db().collection(COLLECTIONS["users"]).document(uid).update({
            "status": new_status, "updated_at": now_iso()
        })
        log_activity("system", "HR Admin",
                     f"{'Deactivated' if new_status=='inactive' else 'Activated'} employee", uid)
        return ok({"status": new_status})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  PROJECTS API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/projects", methods=["GET"])
def list_projects():
    uid = request.args.get("uid")
    try:
        docs = (get_db().collection(COLLECTIONS["projects"])
                .order_by("created_at", direction="DESCENDING")
                .stream())
        projects = []
        for d in docs:
            p = {"id": d.id, **d.to_dict()}
            if uid and uid not in p.get("assigned_employees", []):
                continue
            projects.append(p)
        return ok({"projects": projects})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return err("Project name required")
    proj_id = short_id("PRJ")
    proj = {
        "project_id":         proj_id,
        "name":               data["name"].strip(),
        "description":        data.get("description", ""),
        "assigned_employees": data.get("assigned_employees", []),
        "start_date":         data.get("start_date", today_str()),
        "deadline":           data.get("deadline", ""),
        "status":             "active",
        "progress":           0,
        "created_by":         data.get("created_by", ""),
        "created_at":         now_iso(),
    }
    try:
        ref = get_db().collection(COLLECTIONS["projects"]).add(proj)
        log_activity("system", "HR Admin", "Created project", data["name"])
        return ok({"project": {**proj, "id": ref[1].id}})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/projects/<doc_id>", methods=["PUT"])
def update_project(doc_id):
    data    = request.get_json(silent=True) or {}
    allowed = ["name", "description", "assigned_employees",
               "deadline", "status", "progress"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if "progress" in updates:
        updates["progress"] = max(0, min(100, int(updates["progress"])))
    updates["updated_at"] = now_iso()
    try:
        get_db().collection(COLLECTIONS["projects"]).document(doc_id).update(updates)
        return ok({"id": doc_id})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  TASKS API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    uid = request.args.get("uid")
    try:
        docs  = (get_db().collection(COLLECTIONS["tasks"])
                 .order_by("created_at", direction="DESCENDING")
                 .stream())
        tasks = []
        for d in docs:
            t = {"id": d.id, **d.to_dict()}
            if uid and t.get("assigned_to") != uid:
                continue
            tasks.append(t)
        return ok({"tasks": tasks})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}
    if not data.get("title"):
        return err("Task title required")
    task_id = short_id("TSK")
    task = {
        "task_id":      task_id,
        "title":        data["title"].strip(),
        "description":  data.get("description", ""),
        "assigned_to":  data.get("assigned_to", ""),
        "assigned_name": data.get("assigned_name", ""),
        "priority":     data.get("priority", "medium"),
        "start_date":   data.get("start_date", today_str()),
        "deadline":     data.get("deadline", ""),
        "status":       "pending",
        "completion":   0,
        "project_id":   data.get("project_id", ""),
        "created_by":   data.get("created_by", ""),
        "created_at":   now_iso(),
    }
    try:
        ref = get_db().collection(COLLECTIONS["tasks"]).add(task)
        log_activity("system", "HR Admin", "Assigned task", data["title"])
        return ok({"task": {**task, "id": ref[1].id}})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/tasks/<doc_id>", methods=["PUT"])
def update_task(doc_id):
    data    = request.get_json(silent=True) or {}
    allowed = ["title", "description", "priority", "deadline",
               "status", "completion", "assigned_to", "assigned_name"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if "completion" in updates:
        updates["completion"] = max(0, min(100, int(updates["completion"])))
    updates["updated_at"] = now_iso()
    try:
        get_db().collection(COLLECTIONS["tasks"]).document(doc_id).update(updates)
        return ok({"id": doc_id})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  EOD REPORTS API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/eod", methods=["GET"])
def list_eod():
    uid  = request.args.get("uid")
    date = request.args.get("date")
    try:
        query = get_db().collection(COLLECTIONS["eod_reports"])
        if uid:  query = query.where("employee_id", "==", uid)
        if date: query = query.where("date", "==", date)
        docs  = query.order_by("submitted_at", direction="DESCENDING").stream()
        return ok({"reports": [{"id": d.id, **d.to_dict()} for d in docs]})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/eod", methods=["POST"])
@_rate_limit(20, 60)
def submit_eod():
    data = request.get_json(silent=True) or {}
    for f in ["employee_id", "employee_name", "tasks_completed"]:
        if not data.get(f):
            return err(f"Field '{f}' required")
    now    = datetime.datetime.utcnow()
    report = {
        "employee_id":     data["employee_id"],
        "employee_name":   data["employee_name"],
        "date":            data.get("date", today_str()),
        "tasks_completed": data["tasks_completed"],
        "time_spent":      data.get("time_spent", ""),
        "challenges":      data.get("challenges", ""),
        "tomorrow_plan":   data.get("tomorrow_plan", ""),
        "attachments":     data.get("attachments", []),
        "submitted_at":    now.isoformat(),
        "time_label":      now.strftime("%H:%M"),
    }
    try:
        ref = get_db().collection(COLLECTIONS["eod_reports"]).add(report)
        log_activity(data["employee_id"], data["employee_name"],
                     "Submitted EOD", report["date"])
        return ok({"report": {**report, "id": ref[1].id}})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  STATS & ACTIVITY
# ══════════════════════════════════════════════════════════════════

@app.route("/api/stats", methods=["GET"])
def get_stats():
    try:
        db        = get_db()
        emp_docs  = list(db.collection(COLLECTIONS["users"]).stream())
        proj_docs = list(db.collection(COLLECTIONS["projects"]).stream())
        task_docs = list(db.collection(COLLECTIONS["tasks"]).stream())
        eod_docs  = list(db.collection(COLLECTIONS["eod_reports"])
                           .where("date", "==", today_str()).stream())
        return ok({
            "total_employees":  len(emp_docs),
            "active_employees": sum(1 for d in emp_docs  if d.to_dict().get("status") == "active"),
            "active_projects":  sum(1 for d in proj_docs if d.to_dict().get("status") == "active"),
            "pending_tasks":    sum(1 for d in task_docs
                                    if d.to_dict().get("status") in ("pending", "in_progress")),
            "eod_today":        len(eod_docs),
        })
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/activity", methods=["GET"])
def get_activity():
    limit = min(int(request.args.get("limit", 15)), 50)
    try:
        docs = (get_db().collection(COLLECTIONS["activity_logs"])
                .order_by("ts", direction="DESCENDING")
                .limit(limit)
                .stream())
        return ok({"logs": [{"id": d.id, **d.to_dict()} for d in docs]})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  FILE UPLOAD
# ══════════════════════════════════════════════════════════════════

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".xlsx", ".txt"}

@app.route("/api/upload", methods=["POST"])
@_rate_limit(15, 60)
def upload_file():
    if "file" not in request.files:
        return err("No file provided")
    file = request.files["file"]
    if not file.filename:
        return err("No file selected")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return err(f"File type '{ext}' not allowed")

    uid  = request.form.get("uid", "unknown")
    try:
        bucket = get_bucket()
        ts     = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe   = "".join(c for c in file.filename if c.isalnum() or c in "._-")
        path   = f"eod_attachments/{uid}/{ts}_{safe}"
        blob   = bucket.blob(path)
        blob.upload_from_file(file, content_type=file.content_type)
        blob.make_public()
        logger.info(f"File uploaded: {path}")
        return ok({"url": blob.public_url, "name": file.filename})
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        init_firebase()
    except RuntimeError as e:
        logger.warning(str(e))
    app.run(
        debug=app.config["DEBUG"],
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
    )
