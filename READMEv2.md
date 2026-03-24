# ⚡ LynxPort — KrisLynx Workforce Operating System

> The Digital Headquarters of KrisLynx LLP

LynxPort is a production-grade HR & Payroll management platform built for KrisLynx LLP. It serves as the central nervous system for workforce operations — from employee management and payroll to task tracking, grievance redressal, and internal communications.

---

## 🏗️ Architecture

| Layer | Technology |
|-------|-----------|
| **Frontend** | HTML5 + CSS3 (Custom Design System) + Vanilla JavaScript |
| **Backend** | Python Flask (Modular API Architecture) |
| **Database** | Google Cloud Firestore (Firebase) |
| **Auth** | Firebase Authentication (Email/Password + Google SSO) |
| **Storage** | Firebase Cloud Storage |
| **Hosting** | Render / Any WSGI-compatible platform |

---

## ✨ Features

### 🎨 UI/UX Design System
- **Light Mode (Default)** — Soft pastels, glassmorphism cards, smooth shadows
- **Dark Mode** — Toggle switch with full theme support
- Micro-interactions, hover animations, responsive design
- Premium SaaS feel (Notion + Zoho HR + Slack inspired)

### 🚀 First-Time Onboarding
- 5-step guided tour for new users
- Skip/Next/Finish controls
- Auto-marked as completed in database

### 👋 Smart Greeting Engine
- Time-based greetings ("Good Morning, Madhu 👋")
- Dynamic insights ("5 pending tasks", "Payroll completed")

### 🔔 Notification Engine
- Real-time bell icon notifications
- Categories: Tasks, Payroll, Leave, HR Announcements, Mail, System
- Mark as read / Mark all read
- HR broadcast to all employees

### 📊 HR Dashboard
- Total Employees, Active/Inactive, Payroll Status
- Task Distribution, Project Overview
- Pending Leaves, Open Grievances
- Activity Feed, Productivity Chart
- **Quick Action Panel**: Send Mail, Assign Task, New Project, Run Payroll, Add Employee, Broadcast

### 👤 Employee Dashboard
- Welcome greeting, Salary overview, Task list
- Leave balance, Notifications feed
- Everything visible in one screen

### 💰 Payroll Engine (EPFO Compliant)
- Basic Salary + HRA + Allowances
- EPF (12% Employee + 12% Employer)
- EPS + EPF split calculation
- Professional Tax deduction
- Bulk payroll run with employee selection
- Auto-notification on payslip generation
- Full payroll history

### 📧 Mail Automation Engine
- Built-in mail composer with templates
- Multi-select employee recipients
- 7 pre-built templates (Task, Payslip, Welcome, Announcement, Leave, etc.)
- Bulk sending with notification triggers

### 📋 Task Management
- Create, assign, track tasks
- Priority levels (Low/Medium/High)
- Status workflow (Pending → In Progress → Completed)
- Progress tracking with visual bars
- Auto-notifications on assignment

### 🏢 Project Management
- Create projects with multi-employee assignment
- Progress tracking, deadline management
- Employee chip-based selection

### 📄 EOD Reports
- Daily submission form
- Challenges and tomorrow's plan
- HR can view all reports by date

### 🏖️ Leave Management
- Leave request submission
- Leave types: Casual, Sick, Earned
- HR approval/rejection workflow
- Auto-notifications on status change
- Leave balance tracking

### ⚠️ Grievance Cell
- Employee complaint submission (General, POSH, Workplace, Other)
- HR review, respond, and resolve
- Status tracking (Open → Resolved → Closed)
- Confidential handling

### 📜 HR Policies
- Code of Conduct
- POSH Policy
- Leave Policy
- Grievance Redressal Policy

### 🪪 ID Card System
- Auto-generated from employee profile
- KrisLynx branding, name, role, department
- Print/Download support

### 👤 Employee Profile
- View personal information
- Leave balance display
- Phone number editing

---

## 📁 Folder Structure

```
lynxport/
├── app.py                 # Main Flask application (all API routes)
├── firebase_config.py     # Firebase initialization & collections
├── requirements.txt       # Python dependencies
├── render.yaml           # Render deployment config
├── .env.example          # Environment variables template
├── static/
│   ├── css/
│   │   └── style.css     # Complete design system
│   └── js/
│       └── shared.js     # Session, UI, notifications, theming
├── templates/
│   ├── base.html         # Base layout with sidebar, topbar, notifications
│   ├── login.html        # Glassmorphism login page
│   ├── error.html        # Error page
│   ├── dashboard_hr.html # HR Dashboard
│   ├── dashboard_employee.html
│   ├── employees.html    # Employee management
│   ├── projects.html     # Project management
│   ├── tasks.html        # Task management
│   ├── eod.html          # EOD Reports
│   ├── payroll.html      # Payroll engine (HR)
│   ├── payslips.html     # Payslips (Employee)
│   ├── mail.html         # Mail center
│   ├── leave.html        # Leave management
│   ├── profile.html      # Employee profile
│   ├── idcard.html       # ID Card
│   ├── policies.html     # HR Policies
│   ├── grievance_emp.html # Employee grievance
│   └── grievance_hr.html  # HR grievance management
└── public/               # Firebase hosting
```

---

## 🚀 Deployment

### Prerequisites
- Python 3.10+
- Firebase project with Firestore, Auth, and Storage enabled

### Local Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# Add your Firebase credentials to .env
python app.py
```

### Render Deployment
- Set all environment variables from `.env.example`
- Set `FIREBASE_SERVICE_ACCOUNT_JSON` as a single-line JSON string

---

## 🔐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/session | Authenticate user |
| POST | /api/auth/create-employee | Create new employee |
| GET/PUT | /api/employees/:uid | Manage employees |
| GET/POST | /api/projects | Manage projects |
| GET/POST | /api/tasks | Manage tasks |
| GET/POST | /api/eod | EOD reports |
| POST | /api/payroll/run | Run bulk payroll |
| GET | /api/payroll | View payroll history |
| GET | /api/notifications | Get notifications |
| POST | /api/notifications/broadcast | HR broadcast |
| POST | /api/mail/send | Send mail |
| GET/POST | /api/leave | Leave management |
| GET/POST | /api/complaints | Grievance management |
| GET | /api/stats | Dashboard statistics |
| GET | /api/activity | Activity feed |

---

**Built with ❤️ by KrisLynx LLP**
