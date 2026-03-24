"""
LynxPort – KrisLynx LLP Workforce Operating System
app.py  |  Production build for Render

Modules: Auth, Employees, Projects, Tasks, EOD, Payroll (EPFO),
         Notifications, Mail, Complaints/Grievance, Leave, Policies, ID Cards
"""

import os, uuid, datetime, json, logging, time, math, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
logger = logging.getLogger("lynxport")

# ══════════════════════════════════════════════════════════════════
#  APP FACTORY
# ══════════════════════════════════════════════════════════════════
app = Flask(__name__)
app.config["SECRET_KEY"]          = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["ENV"]                 = os.getenv("FLASK_ENV", "production")
app.config["DEBUG"]               = os.getenv("FLASK_ENV") == "development"
app.config["MAX_CONTENT_LENGTH"]  = 10 * 1024 * 1024
app.config["JSON_SORT_KEYS"]      = False

IS_PROD = app.config["ENV"] == "production"

# ══════════════════════════════════════════════════════════════════
#  IN-PROCESS RATE LIMITER
# ══════════════════════════════════════════════════════════════════
_rate_store: dict[str, list] = defaultdict(list)

def _rate_limit(max_calls: int, window_secs: int):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            ip  = request.headers.get("X-Forwarded-For", request.remote_addr or "anon").split(",")[0].strip()
            now = time.monotonic()
            key = f"{fn.__name__}:{ip}"
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

@app.before_request
def start_timer():
    g.start = time.monotonic()

@app.after_request
def log_request(response):
    dur_ms = round((time.monotonic() - getattr(g, "start", time.monotonic())) * 1000, 1)
    if not request.path.startswith("/static"):
        logger.info(f'{request.method} {request.path} → {response.status_code} ({dur_ms}ms)')
    return response

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

def send_notification(recipient_uid, title, message, category="system", sender_uid="system"):
    """Create a notification record in Firestore."""
    try:
        notif = {
            "recipient_uid": recipient_uid,
            "title": title,
            "message": message,
            "category": category,
            "sender_uid": sender_uid,
            "read": False,
            "created_at": now_iso(),
        }
        get_db().collection(COLLECTIONS["notifications"]).add(notif)
    except Exception as ex:
        logger.warning(f"Notification send failed: {ex}")

def send_bulk_notification(recipient_uids, title, message, category="hr_announcement", sender_uid="system"):
    """Send notification to multiple recipients."""
    for uid in recipient_uids:
        send_notification(uid, title, message, category, sender_uid)

# ── Zoho SMTP Email Sender ─────────────────────────────────────────
ZOHO_SMTP_HOST = os.getenv("ZOHO_SMTP_HOST", "smtp.zoho.in")
ZOHO_SMTP_PORT = int(os.getenv("ZOHO_SMTP_PORT", "587"))
ZOHO_EMAIL     = os.getenv("ZOHO_EMAIL", "")
ZOHO_PASSWORD  = os.getenv("ZOHO_PASSWORD", "")
ZOHO_FROM_NAME = os.getenv("ZOHO_FROM_NAME", "LynxPort - KrisLynx LLP")

def build_html_email(subject, body_text, recipient_name=""):
    """Build a clean professional HTML email."""
    greeting = f"Dear {recipient_name}," if recipient_name else "Dear Team,"
    body_html = body_text.replace("\n", "<br/>")
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fb;padding:32px 0;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.06);">
  <tr><td style="background:linear-gradient(135deg,#6c5ce7,#4834d4);padding:28px 32px;">
    <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.3px;">LynxPort</h1>
    <p style="margin:4px 0 0;color:rgba(255,255,255,0.75);font-size:12px;letter-spacing:0.5px;">KrisLynx LLP - Workforce Operating System</p>
  </td></tr>
  <tr><td style="padding:32px;">
    <h2 style="margin:0 0 20px;color:#1a1d2e;font-size:18px;font-weight:600;">{subject}</h2>
    <div style="color:#4a4a5a;font-size:14px;line-height:1.8;">{body_html}</div>
  </td></tr>
  <tr><td style="padding:0 32px 28px;">
    <table width="100%" style="border-top:1px solid #eee;padding-top:20px;">
    <tr><td>
      <p style="margin:0;color:#999;font-size:12px;">This is an automated message from LynxPort.</p>
      <p style="margin:4px 0 0;color:#999;font-size:12px;">KrisLynx LLP - Igniting Tomorrow's Solutions</p>
    </td></tr></table>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

def send_zoho_email(to_email, to_name, subject, body_text):
    """Send email via Zoho SMTP. Returns True on success."""
    if not ZOHO_EMAIL or not ZOHO_PASSWORD:
        logger.warning("Zoho SMTP credentials not configured. Skipping email send.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"{ZOHO_FROM_NAME} <{ZOHO_EMAIL}>"
        msg["To"]      = to_email
        msg["Subject"] = subject

        # Plain text version
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        # HTML version
        html_content = build_html_email(subject, body_text, to_name)
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP(ZOHO_SMTP_HOST, ZOHO_SMTP_PORT) as server:
            server.starttls()
            server.login(ZOHO_EMAIL, ZOHO_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Zoho email send failed to {to_email}: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
#  SYSTEM ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route("/health")
def health():
    try:
        get_db().collection(COLLECTIONS["users"]).limit(1).get()
        db_ok = True
    except Exception:
        db_ok = False
    status = "ok" if db_ok else "degraded"
    code   = 200  if db_ok else 503
    return jsonify({
        "status":  status,
        "service": "lynxport-workforce-os",
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

# ── HR Pages ──────────────────────────────────────────────────────
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

@app.route("/hr/payroll")
def hr_payroll():       return render_template("payroll.html")

@app.route("/hr/mail")
def hr_mail():          return render_template("mail.html")

@app.route("/hr/policies")
def hr_policies():      return render_template("policies.html")

@app.route("/hr/grievance")
def hr_grievance():     return render_template("grievance_hr.html")

@app.route("/hr/leave")
def hr_leave():         return render_template("leave_hr.html")

# ── Employee Pages ────────────────────────────────────────────────
@app.route("/employee/dashboard")
def emp_dashboard():    return render_template("dashboard_employee.html")

@app.route("/employee/projects")
def emp_projects():     return render_template("projects.html")

@app.route("/employee/tasks")
def emp_tasks():        return render_template("tasks.html")

@app.route("/employee/eod")
def emp_eod():          return render_template("eod.html")

@app.route("/employee/profile")
def emp_profile():      return render_template("profile.html")

@app.route("/employee/payslips")
def emp_payslips():     return render_template("payslips.html")

@app.route("/employee/leave")
def emp_leave():        return render_template("leave.html")

@app.route("/employee/grievance")
def emp_grievance():    return render_template("grievance_emp.html")

@app.route("/employee/policies")
def emp_policies():     return render_template("policies.html")

@app.route("/employee/idcard")
def emp_idcard():       return render_template("idcard.html")

# ══════════════════════════════════════════════════════════════════
#  AUTH API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/auth/session", methods=["POST"])
@_rate_limit(30, 60)
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
                "position": "", "phone": "", "profile_image": "",
                "join_date": today_str(), "created_at": now_iso(),
                "onboarded": False,
                "salary_basic": 0, "salary_hra": 0, "salary_allowances": 0,
                "leave_balance": {"casual": 12, "sick": 6, "earned": 15},
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
            "uid":            user_record.uid,
            "employee_id":    emp_id,
            "name":           data["name"].strip(),
            "email":          data["email"].lower().strip(),
            "department":     data.get("department", ""),
            "role":           data.get("role", "employee"),
            "position":       data.get("position", ""),
            "phone":          data.get("phone", ""),
            "join_date":      data.get("join_date", today_str()),
            "status":         "active",
            "profile_image":  "",
            "created_at":     now_iso(),
            "onboarded":      False,
            "salary_basic":      float(data.get("salary_basic", 0)),
            "salary_hra":        float(data.get("salary_hra", 0)),
            "salary_allowances": float(data.get("salary_allowances", 0)),
            "leave_balance": {"casual": 12, "sick": 6, "earned": 15},
        }
        get_db().collection(COLLECTIONS["users"]).document(user_record.uid).set(profile)
        log_activity("system", "HR Admin", "Created employee", f"{data['name']} ({emp_id})")

        # Send welcome notification
        send_notification(user_record.uid, "Welcome to KrisLynx!",
                          f"Hello {data['name']}, welcome to the KrisLynx family. Explore LynxPort to get started.",
                          "system")

        logger.info(f"Employee created: {emp_id} {data['email']}")
        return ok({"profile": profile})
    except Exception as e:
        logger.error(f"create_employee error: {e}")
        return err(str(e), 500)


@app.route("/api/auth/onboarded", methods=["POST"])
def mark_onboarded():
    data = request.get_json(silent=True) or {}
    uid = data.get("uid")
    if not uid:
        return err("uid required")
    try:
        get_db().collection(COLLECTIONS["users"]).document(uid).update({"onboarded": True})
        return ok()
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  EMPLOYEES API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/employees", methods=["GET"])
def list_employees():
    try:
        docs = get_db().collection(COLLECTIONS["users"]).stream()
        emps = sorted([d.to_dict() for d in docs], key=lambda x: x.get("name", "").lower())
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
               "status", "profile_image", "salary_basic", "salary_hra",
               "salary_allowances", "leave_balance"]
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
                .order_by("created_at", direction="DESCENDING").stream())
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

        # Notify assigned employees
        for emp_uid in proj["assigned_employees"]:
            send_notification(emp_uid, "New Project Assignment",
                              f"You've been assigned to project: {proj['name']}",
                              "task", "system")

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
                 .order_by("created_at", direction="DESCENDING").stream())
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
        "task_id":       task_id,
        "title":         data["title"].strip(),
        "description":   data.get("description", ""),
        "assigned_to":   data.get("assigned_to", ""),
        "assigned_name": data.get("assigned_name", ""),
        "priority":      data.get("priority", "medium"),
        "start_date":    data.get("start_date", today_str()),
        "deadline":      data.get("deadline", ""),
        "status":        "pending",
        "completion":    0,
        "project_id":    data.get("project_id", ""),
        "created_by":    data.get("created_by", ""),
        "created_at":    now_iso(),
    }
    try:
        ref = get_db().collection(COLLECTIONS["tasks"]).add(task)
        log_activity("system", "HR Admin", "Assigned task", data["title"])

        # Auto-notify assigned employee
        if task["assigned_to"]:
            send_notification(task["assigned_to"], "New Task Assigned",
                              f"You have a new task: {task['title']}",
                              "task", "system")

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

        # Auto-notify on completion
        if updates.get("status") == "completed":
            doc = get_db().collection(COLLECTIONS["tasks"]).document(doc_id).get()
            if doc.exists:
                task_data = doc.to_dict()
                send_notification("system", "Task Completed",
                                  f"Task '{task_data.get('title')}' completed by {task_data.get('assigned_name')}",
                                  "task")

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
        docs  = query.stream()
        reports = [{"id": d.id, **d.to_dict()} for d in docs]
        reports.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
        return ok({"reports": reports})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/eod", methods=["POST"])
@_rate_limit(20, 60)
def submit_eod():
    data = request.get_json(silent=True) or {}
    for f in ["employee_id", "employee_name", "tasks_completed"]:
        if not data.get(f):
            return err(f"Field '{f}' required")
    now_dt = datetime.datetime.utcnow()
    report = {
        "employee_id":     data["employee_id"],
        "employee_name":   data["employee_name"],
        "date":            data.get("date", today_str()),
        "tasks_completed": data["tasks_completed"],
        "time_spent":      data.get("time_spent", ""),
        "challenges":      data.get("challenges", ""),
        "tomorrow_plan":   data.get("tomorrow_plan", ""),
        "attachments":     data.get("attachments", []),
        "submitted_at":    now_dt.isoformat(),
        "time_label":      now_dt.strftime("%H:%M"),
    }
    try:
        ref = get_db().collection(COLLECTIONS["eod_reports"]).add(report)
        log_activity(data["employee_id"], data["employee_name"],
                     "Submitted EOD", report["date"])
        return ok({"report": {**report, "id": ref[1].id}})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  PAYROLL ENGINE (EPFO COMPLIANT)
# ══════════════════════════════════════════════════════════════════

def calculate_epfo(basic_salary):
    """Calculate EPFO contributions based on Indian law."""
    # EPF wage ceiling for calculation
    epf_wage = min(basic_salary, 15000)

    employee_pf = round(basic_salary * 0.12, 2)         # 12% of basic
    employer_pf_total = round(basic_salary * 0.12, 2)    # 12% of basic

    # Employer's share split:
    eps = round(min(epf_wage, basic_salary) * 0.0833, 2) # 8.33% to EPS (max on 15000)
    employer_epf = round(employer_pf_total - eps, 2)      # Remaining to EPF

    return {
        "employee_pf": employee_pf,
        "employer_pf_total": employer_pf_total,
        "employer_epf": employer_epf,
        "eps": eps,
    }


@app.route("/api/payroll/calculate", methods=["POST"])
def calculate_payroll():
    """Calculate payroll for a single employee."""
    data = request.get_json(silent=True) or {}
    basic       = float(data.get("basic", 0))
    hra         = float(data.get("hra", 0))
    allowances  = float(data.get("allowances", 0))
    deductions  = float(data.get("deductions", 0))

    gross = basic + hra + allowances
    epfo  = calculate_epfo(basic)

    professional_tax = 200 if gross > 15000 else 0  # Standard PT for most states

    total_deductions = epfo["employee_pf"] + deductions + professional_tax
    net_salary       = round(gross - total_deductions, 2)

    return ok({
        "breakdown": {
            "basic": basic,
            "hra": hra,
            "allowances": allowances,
            "gross": gross,
            "epfo": epfo,
            "professional_tax": professional_tax,
            "other_deductions": deductions,
            "total_deductions": round(total_deductions, 2),
            "net_salary": net_salary,
        }
    })


@app.route("/api/payroll/run", methods=["POST"])
def run_payroll():
    """Run payroll for selected employees for a given month."""
    data = request.get_json(silent=True) or {}
    month       = data.get("month", datetime.datetime.utcnow().strftime("%Y-%m"))
    employee_ids = data.get("employee_uids", [])

    if not employee_ids:
        return err("No employees selected")

    db = get_db()
    results = []

    try:
        for uid in employee_ids:
            doc = db.collection(COLLECTIONS["users"]).document(uid).get()
            if not doc.exists:
                continue
            emp = doc.to_dict()

            basic      = float(emp.get("salary_basic", 0))
            hra        = float(emp.get("salary_hra", 0))
            allowances = float(emp.get("salary_allowances", 0))
            gross      = basic + hra + allowances
            epfo       = calculate_epfo(basic)
            pt         = 200 if gross > 15000 else 0
            total_ded  = epfo["employee_pf"] + pt
            net        = round(gross - total_ded, 2)

            payslip_id = short_id("PAY")
            record = {
                "payslip_id":     payslip_id,
                "employee_uid":   uid,
                "employee_id":    emp.get("employee_id", ""),
                "employee_name":  emp.get("name", ""),
                "department":     emp.get("department", ""),
                "position":       emp.get("position", ""),
                "month":          month,
                "basic":          basic,
                "hra":            hra,
                "allowances":     allowances,
                "gross":          gross,
                "employee_pf":    epfo["employee_pf"],
                "employer_pf":    epfo["employer_pf_total"],
                "employer_epf":   epfo["employer_epf"],
                "eps":            epfo["eps"],
                "professional_tax": pt,
                "total_deductions": round(total_ded, 2),
                "net_salary":     net,
                "status":         "generated",
                "generated_at":   now_iso(),
            }
            db.collection(COLLECTIONS["payroll"]).add(record)

            # Auto-notify employee
            send_notification(uid, "Payslip Generated",
                              f"Your payslip for {month} is ready. Net salary: ₹{net:,.2f}",
                              "payroll")

            results.append(record)

        log_activity("system", "HR Admin", "Ran payroll", f"{month} for {len(results)} employees")
        return ok({"payslips": results, "count": len(results)})
    except Exception as e:
        logger.error(f"Payroll run error: {e}")
        return err(str(e), 500)


@app.route("/api/payroll", methods=["GET"])
def list_payroll():
    uid   = request.args.get("uid")
    month = request.args.get("month")
    try:
        query = get_db().collection(COLLECTIONS["payroll"])
        if uid:   query = query.where("employee_uid", "==", uid)
        if month: query = query.where("month", "==", month)
        docs = query.stream()
        payslips = [{"id": d.id, **d.to_dict()} for d in docs]
        payslips.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
        return ok({"payslips": payslips})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  NOTIFICATIONS API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/notifications", methods=["GET"])
def list_notifications():
    uid = request.args.get("uid")
    if not uid:
        return err("uid required")
    try:
        docs = (get_db().collection(COLLECTIONS["notifications"])
                .where("recipient_uid", "==", uid)
                .limit(50).stream())
        notifs = [{"id": d.id, **d.to_dict()} for d in docs]
        # Sort in Python to avoid Firestore composite index requirement
        notifs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return ok({"notifications": notifs})
    except Exception as e:
        logger.error(f"Notifications error: {e}")
        return ok({"notifications": []})


@app.route("/api/notifications/<doc_id>/read", methods=["POST"])
def mark_notification_read(doc_id):
    try:
        get_db().collection(COLLECTIONS["notifications"]).document(doc_id).update({"read": True})
        return ok()
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/notifications/read-all", methods=["POST"])
def mark_all_read():
    data = request.get_json(silent=True) or {}
    uid  = data.get("uid")
    if not uid:
        return err("uid required")
    try:
        docs = (get_db().collection(COLLECTIONS["notifications"])
                .where("recipient_uid", "==", uid)
                .stream())
        for d in docs:
            if d.to_dict().get("read") == False:
                d.reference.update({"read": True})
        return ok()
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/notifications/broadcast", methods=["POST"])
def broadcast_notification():
    """HR broadcasts notification to all or selected employees."""
    data = request.get_json(silent=True) or {}
    title   = data.get("title", "")
    message = data.get("message", "")
    targets = data.get("targets", [])  # Empty = all employees

    if not title or not message:
        return err("Title and message required")

    try:
        if not targets:
            docs = get_db().collection(COLLECTIONS["users"]).stream()
            targets = [d.to_dict().get("uid") for d in docs if d.to_dict().get("uid")]

        send_bulk_notification(targets, title, message, "hr_announcement",
                               data.get("sender_uid", "system"))
        return ok({"sent_to": len(targets)})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  MAIL API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/mail/send", methods=["POST"])
@_rate_limit(20, 60)
def send_mail():
    """Send email via Zoho SMTP to selected employees."""
    data = request.get_json(silent=True) or {}
    recipients = data.get("recipients", [])
    subject    = data.get("subject", "")
    body       = data.get("body", "")
    template   = data.get("template", "custom")

    if not recipients or not subject:
        return err("Recipients and subject required")

    sent_count = 0
    failed = []

    for r in recipients:
        email = r.get("email", "")
        name  = r.get("name", "")
        if not email:
            continue

        # Personalize body
        personalized = body.replace("{name}", name).replace("{email}", email)

        success = send_zoho_email(email, name, subject, personalized)
        if success:
            sent_count += 1
        else:
            failed.append(email)

    # Log to Firestore
    mail_log = {
        "recipients":   recipients,
        "subject":      subject,
        "body":         body,
        "template":     template,
        "sent_by":      data.get("sent_by", "system"),
        "sent_at":      now_iso(),
        "status":       "sent" if sent_count > 0 else "failed",
        "sent_count":   sent_count,
        "failed_count": len(failed),
        "failed_emails": failed,
    }
    try:
        ref = get_db().collection(COLLECTIONS["mail_logs"]).add(mail_log)

        # Notify recipients in LynxPort
        for r in recipients:
            if r.get("uid"):
                send_notification(r["uid"], f"New Mail: {subject}",
                                  body[:200], "mail", data.get("sent_by", "system"))

        log_activity(data.get("sent_by", "system"), "HR Admin",
                     "Sent mail", f"{subject} to {sent_count}/{len(recipients)} recipients")

        return ok({
            "mail_id": ref[1].id,
            "sent_count": sent_count,
            "failed_count": len(failed),
            "failed_emails": failed,
        })
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/mail/logs", methods=["GET"])
def list_mail_logs():
    try:
        docs = (get_db().collection(COLLECTIONS["mail_logs"])
                .order_by("sent_at", direction="DESCENDING")
                .limit(50).stream())
        return ok({"mails": [{"id": d.id, **d.to_dict()} for d in docs]})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  LEAVE MANAGEMENT API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/leave", methods=["GET"])
def list_leave():
    uid    = request.args.get("uid")
    status = request.args.get("status")
    try:
        query = get_db().collection(COLLECTIONS["leave_requests"])
        if uid:    query = query.where("employee_uid", "==", uid)
        if status: query = query.where("status", "==", status)
        docs = query.stream()
        leaves = [{"id": d.id, **d.to_dict()} for d in docs]
        leaves.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return ok({"leaves": leaves})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/leave", methods=["POST"])
def request_leave():
    data = request.get_json(silent=True) or {}
    for f in ["employee_uid", "employee_name", "leave_type", "start_date", "end_date", "reason"]:
        if not data.get(f):
            return err(f"Field '{f}' required")
    leave = {
        "leave_id":      short_id("LV"),
        "employee_uid":  data["employee_uid"],
        "employee_name": data["employee_name"],
        "leave_type":    data["leave_type"],
        "start_date":    data["start_date"],
        "end_date":      data["end_date"],
        "days":          data.get("days", 1),
        "reason":        data["reason"],
        "status":        "pending",
        "created_at":    now_iso(),
    }
    try:
        ref = get_db().collection(COLLECTIONS["leave_requests"]).add(leave)
        # Notify HR
        send_notification("system", "Leave Request",
                          f"{data['employee_name']} requested {data['leave_type']} leave ({data['start_date']} to {data['end_date']})",
                          "leave")
        return ok({"leave": {**leave, "id": ref[1].id}})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/leave/<doc_id>", methods=["PUT"])
def update_leave(doc_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in ("approved", "rejected"):
        return err("Status must be 'approved' or 'rejected'")
    try:
        get_db().collection(COLLECTIONS["leave_requests"]).document(doc_id).update({
            "status": new_status,
            "reviewed_by": data.get("reviewed_by", "HR"),
            "reviewed_at": now_iso(),
            "review_notes": data.get("notes", ""),
        })
        # Get leave details and notify employee
        doc = get_db().collection(COLLECTIONS["leave_requests"]).document(doc_id).get()
        if doc.exists:
            leave_data = doc.to_dict()
            send_notification(leave_data["employee_uid"],
                              f"Leave {new_status.title()}",
                              f"Your {leave_data['leave_type']} leave request has been {new_status}.",
                              "leave")
        return ok({"id": doc_id, "status": new_status})
    except Exception as e:
        return err(str(e), 500)

# ══════════════════════════════════════════════════════════════════
#  GRIEVANCE / COMPLAINTS API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/complaints", methods=["GET"])
def list_complaints():
    uid = request.args.get("uid")
    try:
        query = get_db().collection(COLLECTIONS["complaints"])
        if uid: query = query.where("submitted_by", "==", uid)
        docs = query.stream()
        complaints = [{"id": d.id, **d.to_dict()} for d in docs]
        complaints.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return ok({"complaints": complaints})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/complaints", methods=["POST"])
def submit_complaint():
    data = request.get_json(silent=True) or {}
    for f in ["submitted_by", "submitted_name", "category", "subject", "description"]:
        if not data.get(f):
            return err(f"Field '{f}' required")
    complaint = {
        "complaint_id":  short_id("GRV"),
        "submitted_by":  data["submitted_by"],
        "submitted_name": data["submitted_name"],
        "category":      data["category"],   # general, posh, workplace, other
        "subject":       data["subject"],
        "description":   data["description"],
        "status":        "open",
        "priority":      data.get("priority", "medium"),
        "created_at":    now_iso(),
        "responses":     [],
    }
    try:
        ref = get_db().collection(COLLECTIONS["complaints"]).add(complaint)
        log_activity(data["submitted_by"], data["submitted_name"],
                     "Submitted complaint", data["subject"])
        return ok({"complaint": {**complaint, "id": ref[1].id}})
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/complaints/<doc_id>", methods=["PUT"])
def update_complaint(doc_id):
    data = request.get_json(silent=True) or {}
    try:
        updates = {}
        if "status" in data:
            updates["status"] = data["status"]
        if "response" in data:
            # Append a new response
            doc = get_db().collection(COLLECTIONS["complaints"]).document(doc_id).get()
            if doc.exists:
                responses = doc.to_dict().get("responses", [])
                responses.append({
                    "text": data["response"],
                    "by": data.get("responded_by", "HR"),
                    "at": now_iso(),
                })
                updates["responses"] = responses
        updates["updated_at"] = now_iso()
        get_db().collection(COLLECTIONS["complaints"]).document(doc_id).update(updates)

        # Notify the complainant
        doc = get_db().collection(COLLECTIONS["complaints"]).document(doc_id).get()
        if doc.exists:
            c = doc.to_dict()
            send_notification(c["submitted_by"], "Grievance Update",
                              f"Your complaint '{c['subject']}' has been updated.",
                              "system")

        return ok({"id": doc_id})
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
        leave_pending = list(db.collection(COLLECTIONS["leave_requests"])
                             .where("status", "==", "pending").stream())
        complaints_open = list(db.collection(COLLECTIONS["complaints"])
                               .where("status", "==", "open").stream())

        return ok({
            "total_employees":   len(emp_docs),
            "active_employees":  sum(1 for d in emp_docs if d.to_dict().get("status") == "active"),
            "inactive_employees": sum(1 for d in emp_docs if d.to_dict().get("status") == "inactive"),
            "active_projects":   sum(1 for d in proj_docs if d.to_dict().get("status") == "active"),
            "total_projects":    len(proj_docs),
            "pending_tasks":     sum(1 for d in task_docs
                                    if d.to_dict().get("status") in ("pending", "in_progress")),
            "completed_tasks":   sum(1 for d in task_docs if d.to_dict().get("status") == "completed"),
            "total_tasks":       len(task_docs),
            "eod_today":         len(eod_docs),
            "pending_leaves":    len(leave_pending),
            "open_complaints":   len(complaints_open),
        })
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/activity", methods=["GET"])
def get_activity():
    limit = min(int(request.args.get("limit", 15)), 50)
    try:
        docs = (get_db().collection(COLLECTIONS["activity_logs"])
                .order_by("ts", direction="DESCENDING")
                .limit(limit).stream())
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

    uid = request.form.get("uid", "unknown")
    try:
        bucket = get_bucket()
        ts     = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe   = "".join(c for c in file.filename if c.isalnum() or c in "._-")
        path   = f"uploads/{uid}/{ts}_{safe}"
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
