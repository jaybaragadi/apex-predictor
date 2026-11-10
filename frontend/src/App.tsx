import { useEffect, useState } from "react";
import { S, fromSlug } from "./data";
import { Dashboard } from "./pages/Dashboard";
import { DriverPage, DriversIndex } from "./pages/Drivers";
import { History } from "./pages/History";
import { Methodology } from "./pages/Methodology";
import { Pathways } from "./pages/Pathways";
import { Simulator } from "./pages/Simulator";

const NAV = [
  { id: "dashboard", label: "Dashboard" },
  { id: "drivers", label: "Drivers" },
  { id: "simulator", label: "What-if" },
  { id: "pathways", label: "Pathways" },
  { id: "history", label: "History" },
  { id: "methodology", label: "Methodology" },
];

const readHash = () => (typeof location !== "undefined" ? location.hash.replace(/^#/, "") : "") || "dashboard";

function store(key: string, value?: string): string | null {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch { /* storage unavailable: fall back to defaults */ }
  return null;
}

export default function App() {
  const [route, setRoute] = useState(readHash);
  const reduce = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [animations, setAnimations] = useState(() => !reduce && store("apex-anim") !== "off");
  const [replay, setReplay] = useState(0);

  useEffect(() => {
    const on = () => { setRoute(readHash()); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const toggleAnim = () => { const v = !animations; setAnimations(v); store("apex-anim", v ? "on" : "off"); };
  const driverId = route.startsWith("driver-") ? fromSlug(route.slice(7)) : undefined;
  const active = driverId ? "drivers" : NAV.some((n) => n.id === route) ? route : "dashboard";
  const updated = new Date(S.meta.generated_at);

  let page;
  if (driverId) page = <DriverPage id={driverId} />;
  else if (active === "drivers") page = <DriversIndex />;
  else if (active === "simulator") page = <Simulator />;
  else if (active === "pathways") page = <Pathways />;
  else if (active === "history") page = <History />;
  else if (active === "methodology") page = <Methodology />;
  else page = <Dashboard animations={animations} replayKey={replay} onReplay={() => setReplay((r) => r + 1)} />;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#dashboard" aria-label="Apex Predictor home">
            <span className="brand-mark" aria-hidden="true" />
            <span className="brand-word">Apex Predictor</span>
            <span className="brand-season">{S.meta.season}</span>
          </a>
          <nav aria-label="Sections">
            {NAV.map((n) => (
              <a key={n.id} href={`#${n.id}`} className={active === n.id ? "on" : ""} aria-current={active === n.id ? "page" : undefined}>{n.label}</a>
            ))}
          </nav>
          <div className="topbar-meta">
            {S.status.clinched ? <a href="#dashboard" className="pill gold">★ Title clinched</a> : <span className="pill alive">● Title open</span>}
            <span className="updated" title={updated.toISOString()}>Updated after R{S.meta.last_round} · {updated.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
            <button className="btn tiny ghost" onClick={toggleAnim} aria-pressed={!animations}>{animations ? "Disable animations" : "Enable animations"}</button>
          </div>
        </div>
      </header>
      <main>{page}</main>
      <footer className="footer">
        <p>Apex Predictor · independent fan analytics, not affiliated with Formula 1 or the FIA. Data: Jolpica F1 API. Mathematical status from official results; probabilities are model estimates.</p>
      </footer>
    </div>
  );
}
