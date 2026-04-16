import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/Button';

const STORAGE_KEY = 'nowva_cookie_consent';

type Consent = 'granted' | 'denied';

function applyConsent(consent: Consent): void {
  window.gtag?.('consent', 'update', {
    ad_storage: consent,
    ad_user_data: consent,
    ad_personalization: consent,
    analytics_storage: consent,
  });
}

export function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Consent | null;
    if (stored) {
      applyConsent(stored);
    } else {
      setVisible(true);
    }
  }, []);

  const handle = (consent: Consent) => {
    localStorage.setItem(STORAGE_KEY, consent);
    applyConsent(consent);
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 md:left-auto md:right-6 md:bottom-6 md:max-w-md z-50 rounded-xl bg-surface/95 backdrop-blur border border-border p-5 shadow-2xl">
      <p className="text-sm text-foreground-secondary leading-relaxed">
        We use cookies for analytics to improve Nowva. Your choice won't affect your experience.
      </p>
      <div className="mt-4 flex gap-2 justify-end">
        <Button variant="ghost" size="sm" onClick={() => handle('denied')}>
          Decline
        </Button>
        <Button variant="primary" size="sm" onClick={() => handle('granted')}>
          Accept
        </Button>
      </div>
    </div>
  );
}
