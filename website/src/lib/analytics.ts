type GtagFn = (...args: unknown[]) => void;

function gtag(): GtagFn | undefined {
  if (typeof window === "undefined") return undefined;
  const fn = (window as { gtag?: GtagFn }).gtag;
  return typeof fn === "function" ? fn : undefined;
}

export function trackEvent(name: string, params?: Record<string, unknown>) {
  gtag()?.("event", name, params ?? {});
}

export function updateConsent(granted: boolean) {
  gtag()?.("consent", "update", {
    analytics_storage: granted ? "granted" : "denied",
  });
  /* AnalyticsGate listens for this to mount gtag.js after a mid-session
     Allow — the script is never loaded before consent. */
  window.dispatchEvent(new Event("nv:consent"));
}
