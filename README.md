# KrisLynx LLP — HR Management Portal

Production-grade HR Portal · Flask + Firebase · Deploy to Render in minutes

---

## Deploy to Render — Step by Step

### 1 · Push code to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/krislynx-hr.git
git push -u origin main
```

> `.gitignore` already excludes `.env` and `serviceAccountKey.json` — never commit these.

---

### 2 · Create a Render Web Service

1. [render.com](https://render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Render auto-reads `render.yaml`:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --config gunicorn.conf.py`
   - Health check: `/health`

---

### 3 · Set Environment Variables on Render

Go to your service → **Environment** tab and add these:

| Variable | Value | Source |
|----------|-------|--------|
| `FIREBASE_SERVICE_ACCOUNT_JSON` | *(full JSON, one line)* | Firebase Console → Project Settings → Service Accounts → Generate New Key → minify |
| `FIREBASE_API_KEY` | `AIzaSy…` | Firebase Console → Project Settings → Your Apps → Web |
| `FIREBASE_AUTH_DOMAIN` | `miyraa-59c25.firebaseapp.com` | Same |
| `FIREBASE_MESSAGING_SENDER_ID` | numeric ID | Same |
| `FIREBASE_APP_ID` | `1:…:web:…` | Same |

> `SECRET_KEY`, `FLASK_ENV`, `FIREBASE_PROJECT_ID`, `FIREBASE_STORAGE_BUCKET` are already set in `render.yaml`.

**Minify the service account JSON (Mac/Linux):**
```bash
python3 -c "import json,sys; print(json.dumps(json.load(open('serviceAccountKey.json'))))"
# Paste the output as FIREBASE_SERVICE_ACCOUNT_JSON
```

---

### 4 · Enable Firebase Services

In [Firebase Console → miyraa-59c25](https://console.firebase.google.com/u/0/project/miyraa-59c25/):

| Service | Location | Action |
|---------|----------|--------|
| Authentication | Auth → Sign-in method | Enable **Email/Password** |
| Firestore | Firestore Database | Create → **Start in test mode** |
| Storage | Storage | Get started |

**Add Firestore security rules for production:**
```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
```

---

### 5 · Create the First HR Admin

**A.** Firebase Console → Authentication → Add user
- Email: `admin@krislynx.com` · Password: (8+ chars) · Copy the UID

**B.** Firestore → `krislynxllp_hr_users` → Add document (ID = UID from A)
```json
{
  "uid":         "z3lwv6ZhGXXxBhwpHbaBZCK71HH3",
  "email":       "admin@krislynx.com",
  "name":        "HR Admin",
  "role":        "hr",
  "status":      "active",
  "employee_id": "EMP001",
  "department":  "HR",
  "position":    "HR Manager",
  "join_date":   "2025-01-01",
  "created_at":  "2025-01-01T00:00:00"
}
```

**C.** Visit your Render URL → sign in → you're in the HR dashboard.

---

## Local Development

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your Firebase values
# Place serviceAccountKey.json in the project root
python app.py                 # → http://localhost:5000
```

---

## Project Structure

```
krislynx_hr/
├── app.py                    # Flask app — API routes, rate limiting, logging
├── firebase_config.py        # Firebase init (env-var + file fallback)
├── gunicorn.conf.py          # Gunicorn workers, timeouts, hooks
├── Procfile                  # Render/Heroku start command
├── render.yaml               # Render deploy config (auto-detected)
├── requirements.txt
├── .env.example
├── .gitignore
│
├── static/
│   ├── css/style.css         # Dark enterprise design system
│   └── js/shared.js          # Auth, API wrapper, token refresh, utilities
│
└── templates/
    ├── base.html             # Shared Jinja2 layout (all pages extend this)
    ├── login.html            # Login — config server-injected
    ├── dashboard_hr.html     # HR: stats, Chart.js, activity feed
    ├── dashboard_employee.html # Employee: profile hero, quick EOD
    ├── employees.html        # Employee management (HR only)
    ├── projects.html         # Project cards with progress
    ├── tasks.html            # Task table with inline updates
    ├── eod.html              # EOD submit + view reports
    └── error.html            # 404 / 500 error page
```

---

## API Reference

| Method | Endpoint | Rate Limit | Description |
|--------|----------|------------|-------------|
| GET | `/health` | — | Render health check + DB ping |
| POST | `/api/auth/session` | 30/min | Verify Firebase token |
| POST | `/api/auth/create-employee` | 10/min | Create employee account |
| GET | `/api/employees` | — | List all employees |
| GET | `/api/employees/:uid` | — | Get employee |
| PUT | `/api/employees/:uid` | — | Update employee |
| POST | `/api/employees/:uid/toggle` | — | Toggle active/inactive |
| GET | `/api/projects[?uid=]` | — | List projects |
| POST | `/api/projects` | — | Create project |
| PUT | `/api/projects/:id` | — | Update project |
| GET | `/api/tasks[?uid=]` | — | List tasks |
| POST | `/api/tasks` | — | Create task |
| PUT | `/api/tasks/:id` | — | Update task |
| GET | `/api/eod[?uid=&date=]` | — | List EOD reports |
| POST | `/api/eod` | 20/min | Submit EOD |
| GET | `/api/stats` | — | Dashboard statistics |
| GET | `/api/activity[?limit=]` | — | Activity log |
| POST | `/api/upload` | 15/min | Upload to Firebase Storage |

---

## Production Checklist

- [ ] Code pushed to GitHub (no secrets committed)
- [ ] Render Web Service created and linked to repo
- [ ] `FIREBASE_SERVICE_ACCOUNT_JSON` set on Render
- [ ] `FIREBASE_API_KEY`, `FIREBASE_APP_ID`, `FIREBASE_MESSAGING_SENDER_ID` set on Render
- [ ] Firebase Auth → Email/Password enabled
- [ ] Firestore database created + security rules set
- [ ] Firebase Storage enabled
- [ ] First HR admin created manually in Firebase Console
- [ ] `/health` endpoint returns `{"status":"ok"}` after deploy
- [ ] (Optional) Custom domain added in Render → Settings
