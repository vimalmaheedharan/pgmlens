import { useEffect, useState } from "react";
import { Portfolio } from "./components/Portfolio";
import { ProgramPage } from "./components/ProgramPage";
import { Shell } from "./components/Shell";
import { ShortcutHelp } from "./components/ShortcutHelp";
import { useFetch, useRoute, useShortcuts } from "./hooks";
import { TABS } from "./lib/route";
import type { ProgramSummary } from "./types";

export default function App() {
  const { route, navigate } = useRoute();
  const programs = useFetch<ProgramSummary[]>("/api/programs");
  const [helpOpen, setHelpOpen] = useState(false);
  const [searchRequest, setSearchRequest] = useState(0);
  const list = programs.data ?? [];

  // With a single program there is nothing to choose: open it directly.
  useEffect(() => {
    if (!route.programId && list.length === 1) navigate({ programId: list[0].id, tab: "overview" }, { replace: true });
  }, [route.programId, list, navigate]);

  useShortcuts({
    go: (key) => {
      const tab = TABS.find((t) => t.key === key);
      if (tab && route.programId) navigate({ programId: route.programId, tab: tab.id });
    },
    search: () => {
      if (!route.programId) return;
      navigate({ programId: route.programId, tab: "risks" });
      setSearchRequest((n) => n + 1);
    },
    help: () => setHelpOpen(true),
    escape: () => {
      if (helpOpen) setHelpOpen(false);
      else if (route.riskId) navigate({ ...route, riskId: null });
    },
  });

  let body;
  if (programs.error) {
    body = (
      <section className="page narrow">
        <div className="notice" role="alert">
          <p>{programs.error}</p>
          <button type="button" onClick={programs.reload}>
            Try again
          </button>
        </div>
      </section>
    );
  } else if (route.programId) {
    body = (
      <ProgramPage
        key={route.programId}
        programId={route.programId}
        tab={route.tab}
        riskId={route.riskId}
        searchRequest={searchRequest}
        navigate={navigate}
      />
    );
  } else if (programs.loading && !programs.data) {
    body = (
      <section className="page" aria-busy="true">
        <p className="muted">Loading…</p>
      </section>
    );
  } else {
    body = <Portfolio programs={list} onOpen={(id) => navigate({ programId: id, tab: "overview" })} />;
  }

  return (
    <Shell
      programs={list}
      currentId={route.programId}
      onSelect={(id) => navigate(id ? { programId: id, tab: "overview" } : {})}
      onHelp={() => setHelpOpen(true)}
    >
      {body}
      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}
    </Shell>
  );
}
