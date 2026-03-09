// ─────────────────────────────────────────────────────────────────────────────
// KrisLynx LLP – HR Portal  |  shared.js  (production build)
// ─────────────────────────────────────────────────────────────────────────────

// ── Session ───────────────────────────────────────────────────────────────────
const Session = {
  set(profile, role, token) {
    localStorage.setItem("kl_profile",  JSON.stringify(profile));
    localStorage.setItem("kl_role",     role);
    localStorage.setItem("kl_token",    token);
    localStorage.setItem("kl_token_ts", Date.now().toString());
  },
  profile() { try { return JSON.parse(localStorage.getItem("kl_profile") || "{}"); } catch { return {}; } },
  role()    { return localStorage.getItem("kl_role")  || "employee"; },
  token()   { return localStorage.getItem("kl_token") || ""; },
  tokenAge(){ return Date.now() - parseInt(localStorage.getItem("kl_token_ts") || "0"); },
  clear()   { ["kl_profile","kl_role","kl_token","kl_token_ts"].forEach(k => localStorage.removeItem(k)); },
  isHR()    { const r = this.role(); return r === "hr" || r === "admin"; },
};

// ── Token refresh (Firebase ID tokens expire after 1 hour) ────────────────────
// We refresh proactively if the token is older than 50 minutes.
const TOKEN_MAX_AGE_MS = 50 * 60 * 1000;

async function getValidToken() {
  if (Session.tokenAge() < TOKEN_MAX_AGE_MS) return Session.token();
  // Token is stale — ask Firebase to refresh it
  try {
    if (window._fbAuth && window._fbAuth.currentUser) {
      const newToken = await window._fbAuth.currentUser.getIdToken(true);
      const profile  = Session.profile();
      Session.set(profile, Session.role(), newToken);
      return newToken;
    }
  } catch(e) {
    console.warn("Token refresh failed:", e);
  }
  return Session.token(); // return old token as fallback
}

// ── API wrapper with automatic retry on 401 ───────────────────────────────────
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

  const res  = await fetch(path, opts);

  // If 401 and not already retried, force-refresh token and retry once
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

// ── Route guards ──────────────────────────────────────────────────────────────
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

// ── Toast notifications ───────────────────────────────────────────────────────
function toast(msg, type = "success") {
  const colours = { success:"#10b981", error:"#ef4444", info:"#6366f1", warn:"#f59e0b" };
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

// ── Formatting ────────────────────────────────────────────────────────────────
function fmtDate(d) {
  if (!d) return "—";
  try { return new Date(d).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}); }
  catch { return d; }
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

// ── Badges ────────────────────────────────────────────────────────────────────
function statusBadge(s) {
  const map = {
    active:"badge--green", inactive:"badge--gray", completed:"badge--blue",
    pending:"badge--amber", in_progress:"badge--indigo", on_hold:"badge--gray", cancelled:"badge--red",
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
  const col = pct>=80?"#10b981":pct>=40?"#6366f1":"#f59e0b";
  const h   = size==="lg"?"8px":"4px";
  return `<div class="prog-wrap" style="height:${h}">
    <div class="prog-fill" style="width:${Math.min(pct,100)}%;background:${col}"></div>
  </div>`;
}

// ── Avatars ───────────────────────────────────────────────────────────────────
const GRADIENTS = [
  "linear-gradient(135deg,#6366f1,#8b5cf6)",
  "linear-gradient(135deg,#06b6d4,#3b82f6)",
  "linear-gradient(135deg,#10b981,#06b6d4)",
  "linear-gradient(135deg,#f59e0b,#ef4444)",
  "linear-gradient(135deg,#ec4899,#8b5cf6)",
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

// ── Sidebar ───────────────────────────────────────────────────────────────────
function buildSidebar(activeKey) {
  const isHR  = Session.isHR();
  const user  = Session.profile();
  const hrNav = [
    {key:"dashboard", href:"/hr/dashboard",  icon:iconGrid,      label:"Dashboard"},
    {key:"employees", href:"/hr/employees",  icon:iconUsers,     label:"Employees"},
    {key:"projects",  href:"/hr/projects",   icon:iconBriefcase, label:"Projects"},
    {key:"tasks",     href:"/hr/tasks",       icon:iconCheck,     label:"Tasks"},
    {key:"eod",       href:"/hr/eod",         icon:iconDoc,       label:"EOD Reports"},
  ];
  const empNav = [
    {key:"dashboard", href:"/employee/dashboard", icon:iconGrid,      label:"Dashboard"},
    {key:"projects",  href:"/employee/projects",  icon:iconBriefcase, label:"My Projects"},
    {key:"tasks",     href:"/employee/tasks",     icon:iconCheck,     label:"My Tasks"},
    {key:"eod",       href:"/employee/eod",       icon:iconDoc,       label:"EOD Report"},
  ];
  const items = (isHR ? hrNav : empNav).map(n => `
    <a href="${n.href}" class="nav-item ${n.key===activeKey?"nav-item--active":""}">
      ${n.icon}<span>${n.label}</span>
    </a>`).join("");

  return `
<aside class="sidebar">
  <div class="sidebar__logo">
    <div class="sidebar__logo-mark">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    </div>
    <div>
      <div class="sidebar__brand">KrisLynx</div>
      <div class="sidebar__tagline">HR Portal</div>
    </div>
  </div>
  <div class="sidebar__role-badge">${isHR?"HR / Admin":"Employee"}</div>
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

// ── Modals ────────────────────────────────────────────────────────────────────
function openModal(id)  { document.getElementById(id)?.classList.add("modal--open"); }
function closeModal(id) { document.getElementById(id)?.classList.remove("modal--open"); }

// ── SVG Icons ─────────────────────────────────────────────────────────────────
const iconGrid       = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>`;
const iconUsers      = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
const iconBriefcase  = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg>`;
const iconCheck      = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`;
const iconDoc        = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`;
