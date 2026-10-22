import { useEffect, useRef } from "react";
import { TABS } from "../lib/route";

export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    return () => previous?.focus?.();
  }, []);
  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="help-title" tabIndex={-1} ref={panel}>
        <h2 id="help-title">Keyboard shortcuts</h2>
        <dl className="shortcuts">
          {TABS.map((t) => (
            <div key={t.id}>
              <dt>
                <kbd>g</kbd> then <kbd>{t.key}</kbd>
              </dt>
              <dd>Go to {t.label.toLowerCase()}</dd>
            </div>
          ))}
          <div>
            <dt>
              <kbd>/</kbd>
            </dt>
            <dd>Search risks</dd>
          </div>
          <div>
            <dt>
              <kbd>Esc</kbd>
            </dt>
            <dd>Close the open panel</dd>
          </div>
          <div>
            <dt>
              <kbd>?</kbd>
            </dt>
            <dd>Show this list</dd>
          </div>
        </dl>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </>
  );
}
