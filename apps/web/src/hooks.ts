import { useCallback, useEffect, useRef, useState } from "react";
import { getJSON } from "./api";
import { buildHash, parseRoute, type Route } from "./lib/route";

export interface FetchState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch JSON for `path` (null = do nothing). Keeps showing old data while reloading. */
export function useFetch<T>(path: string | null): FetchState<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null,
    error: null,
    loading: path !== null,
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (path === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    getJSON<T>(path, controller.signal).then(
      (data) => setState({ data, error: null, loading: false }),
      (error: Error) => {
        if (controller.signal.aborted || error.name === "AbortError") return;
        setState({ data: null, error: error.message, loading: false });
      },
    );
    return () => controller.abort();
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((next: Partial<Route>, options: { replace?: boolean } = {}) => {
    const hash = buildHash(next);
    if (options.replace) {
      window.history.replaceState(null, "", hash);
      setRoute(parseRoute(hash));
    } else {
      window.location.hash = hash;
    }
  }, []);
  return { route, navigate };
}

export interface ShortcutHandlers {
  go: (key: string) => void;
  search: () => void;
  help: () => void;
  escape: () => void;
}

/** `g` then a letter jumps between tabs; `/` searches; `?` opens help; Esc closes panels. */
export function useShortcuts(handlers: ShortcutHandlers) {
  const latest = useRef(handlers);
  latest.current = handlers;
  useEffect(() => {
    let armedAt = 0;
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const typing =
        !!target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable);
      if (event.key === "Escape") return latest.current.escape();
      if (typing) return;
      if (event.key === "/") {
        event.preventDefault();
        return latest.current.search();
      }
      if (event.key === "?") return latest.current.help();
      if (armedAt && Date.now() - armedAt < 1200) {
        armedAt = 0;
        return latest.current.go(event.key.toLowerCase());
      }
      if (event.key === "g") armedAt = Date.now();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
