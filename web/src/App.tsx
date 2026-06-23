import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { DataContext, loadDataset, type Dataset } from "./data";
import Compare from "./pages/Compare";
import Topic from "./pages/Topic";
import Browse from "./pages/Browse";
import Policy from "./pages/Policy";
import AnalysisPage from "./pages/Analysis";

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
      <header className="topbar">
        <Link to="/" className="brand">
          Payer&nbsp;Policy&nbsp;<span>Compare</span>
        </Link>
        <nav>
          <NavLink to="/" end>Compare</NavLink>
          <NavLink to="/report">Report</NavLink>
          <NavLink to="/browse">Browse</NavLink>
        </nav>
        <div className="stats">
          {data.meta.policy_count.toLocaleString()} policies ·{" "}
          {data.meta.cross_payer_topics} cross-payer topics
        </div>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Compare />} />
          <Route path="/report" element={<AnalysisPage />} />
          <Route path="/topic/:id" element={<Topic />} />
          <Route path="/browse" element={<Browse />} />
          <Route path="/policy/:id" element={<Policy />} />
        </Routes>
      </main>
      <footer className="footer">
        Sources:{" "}
        {data.meta.sources.map((s) => `${s.label} (${s.count})`).join(" · ")}
        {" — "}data scraped from public clinical-guideline pages.
      </footer>
    </DataContext.Provider>
  );
}
