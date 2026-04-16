type GtagFn = (command: string, action: string, params?: Record<string, unknown>) => void;

declare global {
  interface Window {
    gtag?: GtagFn;
  }
}

export function trackEvent(name: string, params: Record<string, unknown> = {}): void {
  if (typeof window === 'undefined' || !window.gtag) return;
  window.gtag('event', name, params);
}
