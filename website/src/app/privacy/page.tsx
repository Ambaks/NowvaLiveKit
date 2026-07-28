import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/layout/Footer";
import { ThemedLogo } from "@/components/ui/Logo";
import { CONTACT_EMAIL, SITE_URL } from "@/lib/constants";

const PAGE_TITLE = "Privacy Policy — NOWVA";
const PAGE_DESCRIPTION =
  "What Nowva collects and why: your name and email when you reserve, consent-gated Google Analytics, and nothing else.";

export const metadata: Metadata = {
  title: PAGE_TITLE,
  description: PAGE_DESCRIPTION,
  alternates: {
    canonical: `${SITE_URL}/privacy`,
  },
  openGraph: {
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION,
    url: `${SITE_URL}/privacy`,
    images: [{ url: "/og.png", width: 1200, height: 630 }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION,
    images: ["/og.png"],
  },
};

const LINK_CLASS =
  "text-accent-ink underline decoration-accent-ink/30 underline-offset-2 transition-colors duration-200 hover:text-accent-strong hover:decoration-accent-strong/60";

const HEADING_CLASS = "mt-12 font-display text-xl font-bold tracking-tight text-fg";
const BODY_CLASS = "mt-3 text-sm leading-relaxed text-fg-2 md:text-base";

function ContactLink() {
  return (
    <a href={`mailto:${CONTACT_EMAIL}`} className={LINK_CLASS}>
      {CONTACT_EMAIL}
    </a>
  );
}

export default function PrivacyPage() {
  return (
    <div>
      <header className="border-b border-border">
        <div className="mx-auto flex h-16 max-w-6xl items-center px-5 md:px-8">
          <Link href="/" className="flex items-center gap-3" aria-label="NOWVA — home">
            <ThemedLogo size={30} />
            <span className="font-display text-base font-extrabold tracking-[0.3em] text-fg">
              NOWVA
            </span>
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-[65ch] px-5 py-16 md:py-24">
        <p className="eyebrow">Legal</p>
        <h1 className="mt-3 font-display text-3xl font-extrabold tracking-tight text-fg md:text-4xl">
          Privacy Policy
        </h1>
        <p className="mt-3 font-mono text-[0.68rem] tracking-[0.08em] text-fg-2">
          Last updated July 28, 2026
        </p>

        <p className="mt-8 text-sm leading-relaxed text-fg-2 md:text-base">
          This site exists to introduce the Nowva Rack and take reservations for
          it. We collect very little, and this page describes all of it — in
          plain language, because that&rsquo;s how we&rsquo;d want it explained
          to us.
        </p>

        <h2 className={HEADING_CLASS}>When you reserve a rack</h2>
        <p className={BODY_CLASS}>
          Reserving asks for two things: your name and your email address. We
          store them in our reservations database, hosted on Neon, a
          cloud-hosted Postgres provider. That record is what holds your place
          in line — nothing else about you is collected with it.
        </p>

        <h2 className={HEADING_CLASS}>Emails we send</h2>
        <p className={BODY_CLASS}>
          When you reserve, Resend — our email delivery provider — sends you a
          confirmation and sends us an internal alert so we know you signed up.
          Your address is also added to our Resend audience so we can send
          occasional product updates as the rack moves toward shipping. You can
          opt out of updates anytime via the unsubscribe link in any of those
          emails, or by writing to <ContactLink />. Opting out of updates does
          not cancel your reservation.
        </p>

        <h2 className={HEADING_CLASS}>Analytics — only if you allow it</h2>
        <p className={BODY_CLASS}>
          We use Google Analytics to understand how visitors use this site,
          and it loads only after you press Allow on the consent banner. Until
          then your browser never contacts Google — no script, no cookies,
          nothing is measured. If you do allow it, Google Analytics sets its
          measurement cookies to tell visitors apart. No ads, no tracking
          across sites. Your choice is remembered in your browser; to change
          it later, clear this site&rsquo;s data in your browser and choose
          again.
        </p>

        <h2 className={HEADING_CLASS}>Stored in your browser</h2>
        <p className={BODY_CLASS}>
          A few functional flags live in your browser&rsquo;s local and
          session storage:
          your theme choice (dark or light), whether you&rsquo;ve already seen
          the intro animation this session, and your cookie-consent decision.
          They exist so the site remembers your preferences between visits.
          They never leave your browser.
        </p>

        <h2 className={HEADING_CLASS}>Abuse protection</h2>
        <p className={BODY_CLASS}>
          The reservation endpoint rate-limits abuse. To do that, it stores a
          SHA-256-hashed identifier derived from your IP address — not the
          address itself. Only the last ten minutes of attempts are ever
          counted, and stored hashes older than 24 hours are deleted
          automatically the next time the endpoint is used.
        </p>

        <h2 className={HEADING_CLASS}>Your data, your call</h2>
        <p className={BODY_CLASS}>
          Want to know what we hold about you, correct it, or have it deleted?
          Email <ContactLink /> and we&rsquo;ll take care of it. Note that
          deleting your reservation data means giving up your place in line —
          the reservation is the data.
        </p>

        <h2 className={HEADING_CLASS}>What we don&rsquo;t do</h2>
        <p className={BODY_CLASS}>
          We don&rsquo;t sell your data. We don&rsquo;t run ads. We don&rsquo;t
          track you across other sites. And we don&rsquo;t collect anything
          this page doesn&rsquo;t mention.
        </p>

        <h2 className={HEADING_CLASS}>Changes to this policy</h2>
        <p className={BODY_CLASS}>
          If this policy changes, we&rsquo;ll update this page and revise the
          date at the top. If a change meaningfully affects reservation
          holders, we&rsquo;ll say so in an update email.
        </p>

        <h2 className={HEADING_CLASS}>Contact</h2>
        <p className={BODY_CLASS}>
          Questions about any of this? Email <ContactLink /> — a human reads
          every message.
        </p>
      </main>

      <Footer />
    </div>
  );
}
