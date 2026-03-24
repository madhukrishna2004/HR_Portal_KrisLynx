// ═══════════════════════════════════════════════════════════════
// LynxPort – KrisLynx Workforce Operating System
// shared.js  |  Production build
// ═══════════════════════════════════════════════════════════════

// ── Session ──────────────────────────────────────────────────────
const Session = {
  set(profile, role, token) {
    localStorage.setItem("lp_profile",  JSON.stringify(profile));
    localStorage.setItem("lp_role",     role);
    localStorage.setItem("lp_token",    token);
    localStorage.setItem("lp_token_ts", Date.now().toString());
  },
  profile() { try { return JSON.parse(localStorage.getItem("lp_profile") || "{}"); } catch { return {}; } },
  role()    { return localStorage.getItem("lp_role")  || "employee"; },
  token()   { return localStorage.getItem("lp_token") || ""; },
  tokenAge(){ return Date.now() - parseInt(localStorage.getItem("lp_token_ts") || "0"); },
  clear()   { ["lp_profile","lp_role","lp_token","lp_token_ts"].forEach(k => localStorage.removeItem(k)); },
  isHR()    { const r = this.role(); return r === "hr" || r === "admin"; },
};

// ── Token refresh ────────────────────────────────────────────────
const TOKEN_MAX_AGE_MS = 50 * 60 * 1000;

async function getValidToken() {
  if (Session.tokenAge() < TOKEN_MAX_AGE_MS) return Session.token();
  try {
    if (window._fbAuth && window._fbAuth.currentUser) {
      const newToken = await window._fbAuth.currentUser.getIdToken(true);
      Session.set(Session.profile(), Session.role(), newToken);
      return newToken;
    }
  } catch(e) {
    console.warn("Token refresh failed:", e);
  }
  return Session.token();
}

// ── API wrapper ──────────────────────────────────────────────────
async function api(path, method = "GET", body = null, retried = false) {
  const token = await getValidToken();
  const opts  = {
    method,
    headers: {
      "Content-Type":  "application/json",
      "Authorization": `Bearer ${token}`,
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (res.status === 401 && !retried) {
    try {
      if (window._fbAuth?.currentUser) {
        const newToken = await window._fbAuth.currentUser.getIdToken(true);
        Session.set(Session.profile(), Session.role(), newToken);
        return api(path, method, body, true);
      }
    } catch(e) {
      logout(); return { ok: false, error: "Session expired" };
    }
  }
  return res.json();
}

// ── Route guards ─────────────────────────────────────────────────
function requireAuth() {
  if (!Session.token()) { window.location.href = "/login"; return false; }
  return true;
}
function requireHR() {
  if (!requireAuth()) return false;
  if (!Session.isHR()) { window.location.href = "/employee/dashboard"; return false; }
  return true;
}
function logout() {
  if (window._fbAuth) {
    try { window._fbAuth.signOut(); } catch(e) {}
  }
  Session.clear();
  window.location.href = "/login";
}

// ── Theme Toggle ─────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem("lp_theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeIcon(saved);
}
function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("lp_theme", next);
  updateThemeIcon(next);
}
function updateThemeIcon(theme) {
  const el = document.getElementById("theme-icon");
  if (!el) return;
  el.innerHTML = theme === "dark"
    ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
    : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
}
initTheme();

// ── Toast ────────────────────────────────────────────────────────
function toast(msg, type = "success") {
  const colours = { success:"#00b894", error:"#e17055", info:"#6c5ce7", warn:"#fdcb6e" };
  const el = Object.assign(document.createElement("div"), {
    className: "kl-toast",
    innerHTML: `<span class="kl-toast-dot" style="background:${colours[type]||colours.info}"></span>${msg}`,
  });
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("kl-toast--show"));
  setTimeout(() => {
    el.classList.remove("kl-toast--show");
    setTimeout(() => el.remove(), 350);
  }, 3200);
}

// ── Formatting ───────────────────────────────────────────────────
function fmtDate(d) {
  if (!d) return "—";
  try { return new Date(d).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}); }
  catch { return d; }
}
function fmtCurrency(n) {
  return "₹" + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}
function timeAgo(ts) {
  if (!ts) return "";
  const diff = Math.floor((Date.now() - new Date(ts)) / 1000);
  if (diff < 60)    return "Just now";
  if (diff < 3600)  return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}
function initials(name = "?") {
  return name.split(" ").slice(0,2).map(w => w[0] || "?").join("").toUpperCase();
}
function escHtml(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── Smart Greeting ───────────────────────────────────────────────
function getGreeting(name) {
  const h = new Date().getHours();
  let greet = "Hello";
  if (h < 12) greet = "Good Morning";
  else if (h < 17) greet = "Good Afternoon";
  else greet = "Good Evening";
  return `${greet}, ${name || "there"}`;
}

// ── Badges ───────────────────────────────────────────────────────
function statusBadge(s) {
  const map = {
    active:"badge--green", inactive:"badge--gray", completed:"badge--blue",
    pending:"badge--amber", in_progress:"badge--indigo", on_hold:"badge--gray",
    cancelled:"badge--red", approved:"badge--green", rejected:"badge--red",
    open:"badge--amber", resolved:"badge--green", closed:"badge--gray",
    generated:"badge--blue", sent:"badge--green",
  };
  const labels = { in_progress:"In Progress" };
  const label  = labels[s] || (s ? s.charAt(0).toUpperCase() + s.slice(1) : "—");
  return `<span class="badge ${map[s]||"badge--gray"}">${escHtml(label)}</span>`;
}
function priorityBadge(p) {
  const map = { high:"badge--red", medium:"badge--amber", low:"badge--green" };
  return `<span class="badge ${map[p]||"badge--gray"}">${escHtml((p||"?").toUpperCase())}</span>`;
}
function progressBar(pct=0, size="sm") {
  const col = pct>=80?"#00b894":pct>=40?"#6c5ce7":"#fdcb6e";
  const h   = size==="lg"?"8px":"5px";
  return `<div class="prog-wrap" style="height:${h}">
    <div class="prog-fill" style="width:${Math.min(pct,100)}%;background:${col}"></div>
  </div>`;
}

// ── Avatars ──────────────────────────────────────────────────────
const GRADIENTS = [
  "linear-gradient(135deg,#6c5ce7,#a29bfe)",
  "linear-gradient(135deg,#4f9cf7,#6c5ce7)",
  "linear-gradient(135deg,#00b894,#00cec9)",
  "linear-gradient(135deg,#fdcb6e,#e17055)",
  "linear-gradient(135deg,#fd79a8,#6c5ce7)",
  "linear-gradient(135deg,#00cec9,#4f9cf7)",
];
function pickGrad(str="") {
  let n = 0;
  for (const c of str) n += c.charCodeAt(0);
  return GRADIENTS[n % GRADIENTS.length];
}
function avatar(name, size=36, gradient) {
  const g = gradient || pickGrad(name);
  return `<div class="avatar" style="width:${size}px;height:${size}px;background:${g};font-size:${Math.round(size*.35)}px">${initials(name)}</div>`;
}

// ── Notifications ────────────────────────────────────────────────
let _notifOpen = false;
async function loadNotifications() {
  const uid = Session.profile().uid;
  if (!uid) return;
  try {
    const res = await api(`/api/notifications?uid=${uid}`);
    if (!res.ok) return;
    const notifs = res.notifications || [];
    const unread = notifs.filter(n => !n.read).length;

    // Update bell count
    const countEl = document.getElementById("notif-count");
    if (countEl) {
      countEl.textContent = unread;
      countEl.style.display = unread > 0 ? "grid" : "none";
    }

    // Render list
    const listEl = document.getElementById("notif-list");
    if (listEl) {
      if (notifs.length === 0) {
        listEl.innerHTML = '<div class="empty-state" style="padding:30px"><div class="empty-state__text">No notifications yet</div></div>';
      } else {
        const categoryLabels = {
          task: "T", payroll: "P", leave: "L",
          hr_announcement: "HR", mail: "M", system: "S"
        };
        listEl.innerHTML = notifs.slice(0, 20).map(n => `
          <div class="notif-item ${n.read ? '' : 'notif-item--unread'}" onclick="markNotifRead('${n.id}', this)">
            <div class="notif-item__icon" style="background:var(--primary-bg);font-size:11px;font-weight:700;color:var(--primary)">${categoryLabels[n.category] || 'N'}</div>
            <div class="notif-item__body">
              <div class="notif-item__title">${escHtml(n.title)}</div>
              <div class="notif-item__text">${escHtml(n.message).substring(0, 80)}</div>
              <div class="notif-item__time">${timeAgo(n.created_at)}</div>
            </div>
          </div>
        `).join("");
      }
    }
  } catch(e) {
    console.warn("Notification load failed:", e);
  }
}

async function markNotifRead(id, el) {
  try {
    await api(`/api/notifications/${id}/read`, "POST");
    if (el) el.classList.remove("notif-item--unread");
    loadNotifications();
  } catch(e) {}
}

async function markAllRead() {
  try {
    await api("/api/notifications/read-all", "POST", { uid: Session.profile().uid });
    loadNotifications();
    toast("All notifications marked as read", "info");
  } catch(e) {}
}

function toggleNotifDropdown() {
  const el = document.getElementById("notif-dropdown");
  if (!el) return;
  _notifOpen = !_notifOpen;
  el.classList.toggle("notif-dropdown--open", _notifOpen);
  if (_notifOpen) loadNotifications();
}

// Close dropdown on click outside
document.addEventListener("click", (e) => {
  if (_notifOpen && !e.target.closest(".notif-bell-wrap")) {
    _notifOpen = false;
    const el = document.getElementById("notif-dropdown");
    if (el) el.classList.remove("notif-dropdown--open");
  }
});

// ── Onboarding ───────────────────────────────────────────────────
const ONBOARD_STEPS = [
  { icon: "1", title: "Welcome to LynxPort", text: "Your all-in-one workforce management platform by KrisLynx LLP. Let us take a quick tour of everything you can do here." },
  { icon: "2", title: "Your Dashboard", text: "Your personalized command center. See tasks, salary overview, leave balance, and notifications -- all in one place." },
  { icon: "3", title: "Payroll and Payslips", text: "Salary breakdowns, EPFO calculations, and downloadable payslips -- fully automated and always accessible." },
  { icon: "4", title: "Tasks and Projects", text: "Track your assignments, update progress, and stay on top of deadlines with our intuitive task management system." },
  { icon: "5", title: "Mail and Notifications", text: "Stay connected with real-time notifications, automated emails for task updates, payslips, and HR announcements." },
];

let _onboardStep = 0;

function showOnboarding() {
  const overlay = document.getElementById("onboard-overlay");
  if (!overlay) return;
  overlay.style.display = "flex";
  _onboardStep = 0;
  renderOnboardStep();
}

function renderOnboardStep() {
  const step = ONBOARD_STEPS[_onboardStep];
  const container = document.getElementById("onboard-content");
  if (!container) return;

  const dots = ONBOARD_STEPS.map((_, i) =>
    `<div class="onboard-dot ${i === _onboardStep ? 'onboard-dot--active' : ''}"></div>`
  ).join("");

  const isLast = _onboardStep === ONBOARD_STEPS.length - 1;
  container.innerHTML = `
    <div class="onboard-icon">${step.icon}</div>
    <h2>${step.title}</h2>
    <p>${step.text}</p>
    <div class="onboard-dots">${dots}</div>
    <div class="onboard-actions">
      <button class="btn btn--ghost" onclick="finishOnboarding()">Skip</button>
      <button class="btn btn--primary" onclick="${isLast ? 'finishOnboarding()' : 'nextOnboardStep()'}">
        ${isLast ? 'Get Started' : 'Next →'}
      </button>
    </div>
  `;
}

function nextOnboardStep() {
  if (_onboardStep < ONBOARD_STEPS.length - 1) {
    _onboardStep++;
    renderOnboardStep();
  }
}

function finishOnboarding() {
  const overlay = document.getElementById("onboard-overlay");
  if (overlay) overlay.style.display = "none";
  // Mark as onboarded
  const uid = Session.profile().uid;
  if (uid) {
    api("/api/auth/onboarded", "POST", { uid });
    const p = Session.profile();
    p.onboarded = true;
    Session.set(p, Session.role(), Session.token());
  }
}

// ── Modals ───────────────────────────────────────────────────────
function openModal(id)  { document.getElementById(id)?.classList.add("modal--open"); }
function closeModal(id) { document.getElementById(id)?.classList.remove("modal--open"); }

// ── SVG Icons ────────────────────────────────────────────────────
const iconGrid       = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>`;
const iconUsers      = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
const iconBriefcase  = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg>`;
const iconCheck      = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`;
const iconDoc        = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`;
const iconWallet     = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></svg>`;
const iconMail       = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>`;
const iconShield     = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`;
const iconAlert      = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
const iconUser       = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
const iconCard       = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>`;
const iconCalendar   = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`;

// ── Sidebar Builder ──────────────────────────────────────────────
function buildSidebar(activeKey) {
  const isHR  = Session.isHR();
  const user  = Session.profile();

  const hrNav = [
    {key:"dashboard", href:"/hr/dashboard",  icon:iconGrid,      label:"Dashboard"},
    {key:"employees", href:"/hr/employees",  icon:iconUsers,     label:"Employees"},
    {key:"projects",  href:"/hr/projects",   icon:iconBriefcase, label:"Projects"},
    {key:"tasks",     href:"/hr/tasks",      icon:iconCheck,     label:"Tasks"},
    {key:"eod",       href:"/hr/eod",        icon:iconDoc,       label:"EOD Reports"},
    {key:"_sep1", type:"sep"},
    {key:"payroll",   href:"/hr/payroll",    icon:iconWallet,    label:"Payroll"},
    {key:"mail",      href:"/hr/mail",       icon:iconMail,      label:"Mail Center"},
    {key:"leave",     href:"/hr/leave",      icon:iconCalendar,  label:"Leave Mgmt"},
    {key:"_sep2", type:"sep"},
    {key:"policies",  href:"/hr/policies",   icon:iconShield,    label:"HR Policies"},
    {key:"grievance", href:"/hr/grievance",  icon:iconAlert,     label:"Grievance Cell"},
  ];

  const empNav = [
    {key:"dashboard", href:"/employee/dashboard", icon:iconGrid,      label:"Dashboard"},
    {key:"projects",  href:"/employee/projects",  icon:iconBriefcase, label:"My Projects"},
    {key:"tasks",     href:"/employee/tasks",     icon:iconCheck,     label:"My Tasks"},
    {key:"eod",       href:"/employee/eod",       icon:iconDoc,       label:"EOD Report"},
    {key:"_sep1", type:"sep"},
    {key:"profile",   href:"/employee/profile",   icon:iconUser,      label:"My Profile"},
    {key:"payslips",  href:"/employee/payslips",  icon:iconWallet,    label:"Payslips"},
    {key:"leave",     href:"/employee/leave",     icon:iconCalendar,  label:"Leave"},
    {key:"idcard",    href:"/employee/idcard",    icon:iconCard,      label:"ID Card"},
    {key:"_sep2", type:"sep"},
    {key:"policies",  href:"/employee/policies",  icon:iconShield,    label:"Policies"},
    {key:"grievance", href:"/employee/grievance", icon:iconAlert,     label:"Grievance"},
  ];

  const items = (isHR ? hrNav : empNav).map(n => {
    if (n.type === "sep") return '<div class="sidebar__sep"></div>';
    return `<a href="${n.href}" class="nav-item ${n.key===activeKey?"nav-item--active":""}">
      ${n.icon}<span>${n.label}</span>
    </a>`;
  }).join("");

  return `
<aside class="sidebar">
  <div class="sidebar__logo">
    <div class="sidebar__logo-mark">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
      </svg>
    </div>
    <div>
      <div class="sidebar__brand">LynxPort</div>
      <div class="sidebar__tagline">KrisLynx LLP</div>
    </div>
  </div>
  <div class="sidebar__role-badge">${isHR ? "HR / Admin" : "Employee"}</div>
  <nav class="sidebar__nav">${items}</nav>
  <div class="sidebar__user">
    <div class="sidebar__avatar">${initials(user.name||user.email||"U")}</div>
    <div class="sidebar__user-info">
      <div class="sidebar__user-name">${escHtml(user.name||"User")}</div>
      <div class="sidebar__user-email">${escHtml(user.email||"")}</div>
    </div>
    <button class="sidebar__logout" onclick="logout()" title="Sign out">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
        <polyline points="16 17 21 12 16 7"/>
        <line x1="21" y1="12" x2="9" y2="12"/>
      </svg>
    </button>
  </div>
</aside>`;
}

// ── Initialize Page ──────────────────────────────────────────────
function initPage() {
  // Load notifications every 30 seconds
  loadNotifications();
  setInterval(loadNotifications, 30000);

  // Check onboarding
  const profile = Session.profile();
  if (profile.uid && !profile.onboarded) {
    setTimeout(showOnboarding, 800);
  }
}

// Auto-init on DOMContentLoaded if we have session
document.addEventListener("DOMContentLoaded", () => {
  if (Session.token()) initPage();
});
