import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { DataContext, loadDataset, type Dataset } from "./data";
import Compare from "./pages/Compare";
import Topic from "./pages/Topic";
import Browse from "./pages/Browse";
import Policy from "./pages/Policy";
import AnalysisPage from "./pages/Analysis";

const NAV = [
  { to: "/", label: "Overview", icon: "▦", end: true },
  { to: "/compare", label: "Compare", icon: "⇆" },
  { to: "/browse", label: "Browse", icon: "≣" },
];

export default function App() {
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDataset().then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="loading">Failed to load data: {error}</div>;
  if (!data) return <div className="loading">Loading policy dataset…</div>;

  return (
    <DataContext.Provider value={data}>
      <div className="shell">
        <aside className="sidebar">
          <Link to="/" className="brand">
            <span className="brand-mark">P</span>
            <span className="brand-text">Policy<strong>DB</strong></span>
          </Link>
          <nav className="side-nav">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className="side-link">
                <span className="side-ico">{n.icon}</span>
                <span>{n.label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="side-foot">
            <div className="side-stat">
              <span className="side-stat-n">{data.meta.policy_count.toLocaleString()}</span>
              <span className="side-stat-l">policies</span>
            </div>
            <div className="side-stat">
              <span className="side-stat-n">{data.meta.cross_payer_topics}</span>
              <span className="side-stat-l">cross-payer topics</span>
            </div>
            <p className="side-src">
              {data.meta.sources.map((s) => s.label).join(" · ")} — public
              clinical-guideline data.
            </p>
          </div>
        </aside>

        <main className="main">
          <div className="main-inner">
            <Routes>
              <Route path="/" element={<AnalysisPage />} />
              <Route path="/compare" element={<Compare />} />
              <Route path="/topic/:id" element={<Topic />} />
              <Route path="/browse" element={<Browse />} />
              <Route path="/policy/:id" element={<Policy />} />
            </Routes>
          </div>
        </main>
      </div>
    </DataContext.Provider>
  );
}
