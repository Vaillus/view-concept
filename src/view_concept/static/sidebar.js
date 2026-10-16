/* view-concept — the session sidebar, on the home page and every session page.

   Lists the sessions grouped by project (the main checkout of their repo; explanations,
   which have none, last), the most recently updated project and session first. Above
   them, « active » repeats the sessions whose agent is listening, with their project,
   to switch between the features in progress. Opening
   a session navigates this tab. « + » starts a new feature in a project: the server
   opens a terminal there and starts the agent on a skill.

   It also holds the page's global event stream: `sessions` reloads the list, and `focus`
   (sent by `view-concept open`) moves the tab the user was last on to that session,
   so a new session shows in the open page instead of a new tab. */
(() => {
  const nav = document.getElementById("sidebar");
  if (!nav) return;
  const current = location.pathname.startsWith("/s/") ? decodeURIComponent(location.pathname.split("/").pop()) : "";
  const TAB = Math.random().toString(36).slice(2);
  const ACTIVE = "vc-active-page";
  const COLLAPSED = "vc-sidebar-collapsed";
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* private mode */ } },
  };
  let rows = [];
  let skills = ["view-branch"];

  const h = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
    }
    n.append(...kids);
    return n;
  };
  const base = (path) => path.split("/").filter(Boolean).pop() || path;
  function ago(iso) {
    const s = (Date.now() - new Date(iso)) / 1000;
    if (s < 60) return "now";
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    if (s < 86400 * 30) return `${Math.floor(s / 86400)}d`;
    return new Date(iso).toLocaleDateString();
  }

  function toast(text) {
    let t = document.getElementById("toast");
    if (!t) { t = h("div", { id: "toast", class: "toast" }); document.body.append(t); }
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => (t.hidden = true), 8000);
  }

  /* Projects in order of their latest session (rows come newest first). */
  function groups() {
    const by = new Map();
    for (const r of rows) {
      if (!by.has(r.project)) by.set(r.project, []);
      by.get(r.project).push(r);
    }
    const out = [...by.entries()].filter(([p]) => p);
    if (by.has("")) out.push(["", by.get("")]);
    return out;
  }

  function item(r, withProject) {
    const a = h("a", { class: "sb-item" + (r.slug === current ? " current" : ""), href: `/s/${r.slug}`, title: r.repo || r.slug },
      h("span", { class: "sb-dot" + (r.listening ? " on" : ""), title: r.listening ? "Agent listening" : "" }),
      h("span", { class: "sb-title", text: r.title }));
    if (withProject && r.project) a.append(h("span", { class: "sb-where dim", text: base(r.project) }));
    if (r.pending) a.append(h("span", { class: "badge flag", title: "Comments sent, not resolved yet", text: String(r.pending) }));
    a.append(h("span", { class: "sb-when dim", text: ago(r.updated) }));
    return a;
  }

  function render() {
    const list = h("div", { class: "sb-list" });
    const active = rows.filter((r) => r.listening);
    if (active.length) {
      list.append(h("div", { class: "sb-project sb-active", title: "Sessions whose agent is listening" },
        h("span", { class: "sb-name", text: "active" })));
      for (const r of active) list.append(item(r, true));
    }
    for (const [project, items] of groups()) {
      const head = h("div", { class: "sb-project", title: project || "explanations, tied to no repository" },
        h("span", { class: "sb-name", text: project ? base(project) : "explanations" }));
      if (project) head.append(h("button", { class: "sb-add", title: `New feature in ${project}`, text: "+", onclick: () => openLauncher(project) }));
      list.append(head);
      for (const r of items) list.append(item(r, false));
    }
    if (!rows.length) list.append(h("p", { class: "dim sb-empty", text: "No session yet." }));
    nav.replaceChildren(
      h("div", { class: "sb-head" },
        h("span", { class: "pane-head", text: "sessions" }),
        h("button", { class: "btn", title: "Start a new feature in a project", text: "+ new", onclick: () => openLauncher("") })),
      list);
    nav.querySelector(".sb-item.current")?.scrollIntoView({ block: "nearest" });
  }

  async function load() {
    try { rows = await (await fetch("/api/sessions")).json(); } catch (e) { return; }
    render();
  }

  /* ---- new feature ---- */

  function openLauncher(project) {
    document.querySelector(".launcher")?.remove();
    const projects = groups().map(([p]) => p).filter(Boolean);
    const err = h("p", { class: "error", hidden: true });
    const folder = h("input", { class: "field", list: "sb-projects", value: project || projects[0] || "", placeholder: "/path/to/project", spellcheck: "false" });
    const skill = h("select", { class: "field" }, ...skills.map((s) => h("option", { value: s, text: s })));
    const request = h("textarea", { rows: "4", placeholder: "What the feature is  (⌘↵ to start)" });
    const useTree = h("input", { type: "checkbox" });
    const tree = h("input", { class: "field", placeholder: "worktree name (from the request if empty)", spellcheck: "false", disabled: true });
    useTree.addEventListener("change", () => { tree.disabled = !useTree.checked; });
    const go = h("button", { class: "btn primary", text: "Start in Ghostty" });
    const close = () => box.remove();
    async function start() {
      const text = request.value.trim();
      if (!text) { request.focus(); return; }
      const name = useTree.checked ? (tree.value.trim() || text.split(/\s+/).slice(0, 5).join(" ")) : "";
      go.disabled = true;
      err.hidden = true;
      const r = await fetch("/api/launch", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: folder.value.trim(), request: text, skill: skill.value, worktree: name }),
      });
      const body = await r.json();
      go.disabled = false;
      if (!r.ok) { err.textContent = body.detail; err.hidden = false; return; }
      close();
      toast(`Started in Ghostty: ${body.command}. The page shows the session once the agent opens it.`);
    }
    go.addEventListener("click", start);
    request.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) start();
    });
    const box = h("div", { class: "launcher", onkeydown: (e) => { if (e.key === "Escape") close(); } },
      h("div", { class: "launcher-box" },
        h("div", { class: "pane-head", text: "new feature" }),
        h("label", { text: "project" }), folder,
        h("datalist", { id: "sb-projects" }, ...projects.map((p) => h("option", { value: p }))),
        h("label", { text: "skill" }), skill,
        h("label", { text: "request" }), request,
        h("label", { class: "check" }, useTree, " in a new worktree"), tree,
        err,
        h("div", { class: "composer-actions" }, h("button", { class: "btn", text: "Cancel", onclick: close }), go)));
    box.addEventListener("click", (e) => { if (e.target === box) close(); });
    document.body.append(box);
    request.focus();
  }

  /* ---- the page the user was last on takes `focus` ---- */

  const markActive = () => { if (document.visibilityState === "visible") store.set(ACTIVE, TAB); };
  markActive();
  window.addEventListener("focus", markActive);
  document.addEventListener("visibilitychange", markActive);
  window.addEventListener("pagehide", () => { if (store.get(ACTIVE) === TAB) store.del(ACTIVE); });

  function connect() {
    const es = new EventSource("/api/events");
    es.addEventListener("sessions", load);
    es.addEventListener("focus", (e) => {
      const { slug } = JSON.parse(e.data);
      const active = store.get(ACTIVE);
      if (slug !== current && (!active || active === TAB)) location.href = `/s/${encodeURIComponent(slug)}`;
    });
  }

  /* ---- collapse ---- */

  const toggle = document.getElementById("sidebar-toggle");
  const setCollapsed = (on) => {
    document.body.classList.toggle("sb-collapsed", on);
    store.set(COLLAPSED, on ? "1" : "");
  };
  setCollapsed(store.get(COLLAPSED) === "1");
  toggle?.addEventListener("click", () => setCollapsed(!document.body.classList.contains("sb-collapsed")));

  fetch("/api/skills").then((r) => r.json()).then((s) => { skills = s; }).catch(() => {});
  load();
  connect();
})();
