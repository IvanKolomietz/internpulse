/* InternPulse dashboard: React 18 + htm (no build step) + Chart.js */
const { useState, useEffect, useRef, useMemo } = React;
const html = htm.bind(React.createElement);

const MY_TARGETS = ["Software Engineering", "Data Analytics", "Data Science / ML", "QA / Test", "Quant", "Data Engineering"];
const ROLE_COLORS = {
  "Software Engineering": "#2f6fed",
  "Data Science / ML": "#8b5cf6",
  "Data Analytics": "#0ea5a4",
  "Data Engineering": "#14b8a6",
  "QA / Test": "#f59e0b",
  "Quant": "#e85d75",
  "Hardware": "#94a3b8",
  "Product": "#64748b",
  "Other": "#cbd5e1",
};
const fmt = (n) => (n == null ? "–" : Number(n).toLocaleString());
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function qs(filters, extra = {}) {
  const p = new URLSearchParams();
  if (filters.term) p.set("term", filters.term);
  if (filters.roles.length) p.set("roles", filters.roles.join(","));
  if (filters.active) p.set("active", "1");
  if (filters.country) p.set("country", filters.country);
  if (filters.q) p.set("q", filters.q);
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  return p.toString();
}

async function api(path, filters, extra) {
  const res = await fetch(`/api/${path}?${qs(filters, extra)}`);
  if (!res.ok) throw new Error((await res.json()).error || res.statusText);
  return res.json();
}

function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

function ChartBox({ config, height = 260 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !config) return;
    Chart.defaults.color = css("--muted");
    Chart.defaults.borderColor = css("--border");
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    const chart = new Chart(ref.current, config);
    return () => chart.destroy();
  }, [config]);
  return html`<div class="chart" style=${{ height }}><canvas ref=${ref}></canvas></div>`;
}

function Filters({ options, filters, setFilters, search, setSearch }) {
  const toggleRole = (r) =>
    setFilters((f) => ({ ...f, roles: f.roles.includes(r) ? f.roles.filter((x) => x !== r) : [...f.roles, r] }));
  const isTargets = MY_TARGETS.every((r) => filters.roles.includes(r)) && filters.roles.length === MY_TARGETS.length;
  return html`
    <div class="filters">
      <select aria-label="Term" value=${filters.term} onChange=${(e) => setFilters((f) => ({ ...f, term: e.target.value }))}>
        <option value="">All terms</option>
        ${options.terms.map((t) => html`<option key=${t} value=${t}>${t}</option>`)}
      </select>
      <select aria-label="Country" value=${filters.country} onChange=${(e) => setFilters((f) => ({ ...f, country: e.target.value }))}>
        <option value="">All countries</option>
        ${options.countries.map((c) => html`<option key=${c} value=${c}>${c}</option>`)}
      </select>
      <input type="search" placeholder="Search title or company…" value=${search} onInput=${(e) => setSearch(e.target.value)} />
      <label class="toggle">
        <input type="checkbox" checked=${filters.active} onChange=${(e) => setFilters((f) => ({ ...f, active: e.target.checked }))} />
        Open only
      </label>
      <div class="chips">
        <button class=${"chip preset" + (isTargets ? " on" : "")}
          onClick=${() => setFilters((f) => ({ ...f, roles: isTargets ? [] : MY_TARGETS }))}>★ My targets</button>
        ${options.roles.map((r) => html`
          <button key=${r} class=${"chip" + (filters.roles.includes(r) ? " on" : "")} onClick=${() => toggleRole(r)}>${r}</button>`)}
      </div>
    </div>`;
}

function Kpis({ s }) {
  if (!s) return null;
  const tiles = [
    ["Postings", fmt(s.total), `${fmt(s.companies)} companies`],
    ["Still open", fmt(s.open), s.total ? `${Math.round((100 * s.open) / s.total)}% of postings` : ""],
    ["New this week", fmt(s.last_7_days), `latest ${s.latest_posted || "–"}`],
    ["Closed by week 8", s.closed_by_week_8_pct == null ? "–" : `${s.closed_by_week_8_pct}%`, "of postings 4–8 weeks old"],
    ["Remote", fmt(s.remote), "postings with a remote option"],
  ];
  return html`<div class="kpis">${tiles.map(([l, v, h]) => html`
    <div class="kpi" key=${l}><div class="l">${l}</div><div class="v">${v}</div><div class="h">${h}</div></div>`)}</div>`;
}

function trendConfig(rows) {
  const weeks = [...new Set(rows.map((r) => r.week))].slice(-26);
  const roles = [...new Set(rows.map((r) => r.role))];
  const lookup = new Map(rows.map((r) => [`${r.week}|${r.role}`, r.n]));
  return {
    type: "bar",
    data: {
      labels: weeks,
      datasets: roles.map((role) => ({
        label: role,
        data: weeks.map((w) => lookup.get(`${w}|${role}`) || 0),
        backgroundColor: ROLE_COLORS[role] || ROLE_COLORS.Other,
        borderRadius: 2,
      })),
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10 } } },
      scales: { x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 16 } }, y: { stacked: true, beginAtZero: true } },
    },
  };
}

function openRateConfig(rows) {
  return {
    type: "line",
    data: {
      labels: rows.map((r) => (r.age_weeks >= 12 ? "12+" : String(r.age_weeks))),
      datasets: [{
        label: "% still open",
        data: rows.map((r) => r.open_pct),
        borderColor: css("--accent"),
        backgroundColor: css("--accent-soft"),
        fill: true, tension: 0.3, pointRadius: 3,
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => `${c.parsed.y}% open (n=${rows[c.dataIndex].n})` } },
      },
      scales: {
        x: { title: { display: true, text: "Weeks since posted" }, grid: { display: false } },
        y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } },
      },
    },
  };
}

function hbarConfig(rows, labelKey, color) {
  return {
    type: "bar",
    data: {
      labels: rows.map((r) => r[labelKey]),
      datasets: [{ data: rows.map((r) => r.n), backgroundColor: rows.map((r) => (typeof color === "function" ? color(r) : color)), borderRadius: 3 }],
    },
    options: {
      indexAxis: "y", maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true }, y: { grid: { display: false } } },
    },
  };
}

function Listings({ filters }) {
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const size = 25;
  useEffect(() => setPage(0), [filters]);
  useEffect(() => {
    api("listings", filters, { limit: size, offset: page * size }).then(setData).catch(() => setData(null));
  }, [filters, page]);
  if (!data) return null;
  const pages = Math.max(1, Math.ceil(data.total / size));
  return html`
    <div class="table-scroll">
      <table>
        <thead><tr><th>Company</th><th>Role</th><th>Location</th><th>Posted</th><th></th></tr></thead>
        <tbody>${data.rows.map((r) => html`
          <tr key=${r.id}>
            <td><strong>${r.company}</strong></td>
            <td>${r.title}<br/><span class="badge">${r.role}</span></td>
            <td class="muted">${(r.locations || "").split(" | ").slice(0, 3).join(" · ")}</td>
            <td class="muted" style=${{ whiteSpace: "nowrap" }}>${r.posted}</td>
            <td>${r.active
              ? html`<a href=${r.url} target="_blank" rel="noopener noreferrer">Apply ↗</a>`
              : html`<span class="badge">closed</span>`}</td>
          </tr>`)}
        </tbody>
      </table>
    </div>
    <div class="pager">
      <span class="muted">${fmt(data.total)} results · page ${page + 1} of ${fmt(pages)}</span>
      <button disabled=${page === 0} onClick=${() => setPage(page - 1)}>← Prev</button>
      <button disabled=${page + 1 >= pages} onClick=${() => setPage(page + 1)}>Next →</button>
    </div>`;
}

function App() {
  const [options, setOptions] = useState(null);
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [base, setFilters] = useState({ term: "Summer 2027", roles: MY_TARGETS, active: false, country: "" });
  const filters = useMemo(() => ({ ...base, q }), [base, q]);
  const [d, setD] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => { fetch("/api/options").then((r) => r.json()).then(setOptions).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    const names = ["summary", "trend", "open-rate", "roles", "companies", "regions", "degrees"];
    Promise.all(names.map((n) => api(n, filters)))
      .then((res) => { setD(Object.fromEntries(names.map((n, i) => [n, res[i]]))); setError(null); })
      .catch((e) => setError(e.message));
  }, [filters]);

  const configs = useMemo(() => {
    if (!d.summary) return {};
    return {
      trend: trendConfig(d.trend),
      openRate: openRateConfig(d["open-rate"]),
      roles: hbarConfig(d.roles, "role", (r) => ROLE_COLORS[r.role] || ROLE_COLORS.Other),
      regions: hbarConfig(d.regions, "region", css("--accent")),
      degrees: hbarConfig(d.degrees, "level", css("--accent")),
    };
  }, [d]);

  const firstWeek = d["open-rate"]?.find((r) => r.age_weeks === 1);
  return html`
    <div class="wrap">
      <header>
        <div>
          <h1>Intern<span>Pulse</span></h1>
          <p class="sub">What the tech internship market actually looks like, from ${fmt(d.summary?.total)} real postings.</p>
        </div>
        <div class="stamp">source: SimplifyJobs/Summer2027-Internships</div>
      </header>
      ${options && html`<${Filters} options=${options} filters=${base} setFilters=${setFilters} search=${search} setSearch=${setSearch} />`}
      ${error && html`<p class="error">Error: ${error}</p>`}
      <${Kpis} s=${d.summary} />
      ${firstWeek && d.summary?.closed_by_week_8_pct != null && html`
        <div class="insight"><strong>Apply early.</strong> Only ${firstWeek.open_pct}% of postings are still open a week after going up,
          and ${d.summary.closed_by_week_8_pct}% have closed by week 8.</div>`}
      ${d.summary && html`
        <div class="grid">
          <div class="card span-8"><h2>New postings per week</h2><p class="note">Last 26 weeks, stacked by role family</p><${ChartBox} config=${configs.trend} /></div>
          <div class="card span-4"><h2>How fast postings close</h2><p class="note">% still open by posting age</p><${ChartBox} config=${configs.openRate} /></div>
          <div class="card span-4"><h2>Role mix</h2><p class="note">Classified from job titles</p><${ChartBox} config=${configs.roles} /></div>
          <div class="card span-4"><h2>Top locations</h2><p class="note">State / province / country, on-site</p><${ChartBox} config=${configs.regions} /></div>
          <div class="card span-4"><h2>Degree eligibility</h2><p class="note">Who can apply</p><${ChartBox} config=${configs.degrees} height=${140} />
            <h2 style=${{ marginTop: 14 }}>Top hiring companies</h2>
            <table><tbody>${d.companies.slice(0, 6).map((c) => html`
              <tr key=${c.company}><td>${c.company}</td><td class="num">${c.n}</td><td class="num muted">${c.open} open</td></tr>`)}</tbody></table>
          </div>
          <div class="card span-12"><h2>Listings</h2><p class="note">Open postings first, newest first</p><${Listings} filters=${filters} /></div>
        </div>`}
    </div>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
