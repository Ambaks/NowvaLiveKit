"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { updateConsent } from "@/lib/analytics";

const emptySubscribe = () => () => {};

const readNoConsent = () => {
  try {
    return !localStorage.getItem("nv-consent");
  } catch {
    /* storage unavailable — stay hidden */
    return false;
  }
};

export function CookieBanner() {
  const [dismissed, setDismissed] = useState(false);
  const [introBlocking, setIntroBlocking] = useState(false);
  const noConsent = useSyncExternalStore(
    emptySubscribe,
    readNoConsent,
    () => false,
  );

  /* While the 3D intro overlay owns the page, stay unmounted — the overlay
     inerts only elements present at its own mount, so appearing later would
     leave the consent buttons tabbable underneath it. IntroStage's effect
     runs first (tree order), so data-intro is already "3d" here whenever
     the takeover happened; every finish() path dispatches nv:intro-done. */
  useEffect(() => {
    if (document.documentElement.dataset.intro !== "3d") return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIntroBlocking(true);
    const show = () => setIntroBlocking(false);
    window.addEventListener("nv:intro-done", show);
    return () => window.removeEventListener("nv:intro-done", show);
  }, []);

  const visible = noConsent && !dismissed && !introBlocking;

  const decide = (granted: boolean) => {
    try {
      localStorage.setItem("nv-consent", granted ? "granted" : "denied");
    } catch {
      /* ignore */
    }
    updateConsent(granted);
    setDismissed(true);
  };

  if (!visible) return null;

  return (
    <div
      role="region"
      aria-label="Cookie consent"
      aria-live="polite"
      className="fixed bottom-4 left-4 z-80 max-w-sm rounded-2xl border border-border bg-surface p-5 shadow-2xl"
    >
      <p className="text-sm leading-relaxed text-fg-2">
        We use one analytics cookie to understand how visitors use this page.
        No ads, no tracking across sites.
      </p>
      <div className="mt-4 flex gap-3">
        <button
          type="button"
          onClick={() => decide(true)}
          className="rounded-full bg-fg px-4 py-2 text-sm font-medium text-bg transition-opacity hover:opacity-85"
        >
          Allow
        </button>
        <button
          type="button"
          onClick={() => decide(false)}
          className="rounded-full border border-border px-4 py-2 text-sm text-fg-2 transition-colors hover:text-fg"
        >
          Decline
        </button>
      </div>
    </div>
  );
}
