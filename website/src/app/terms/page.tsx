import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/layout/Footer";
import { ThemedLogo } from "@/components/ui/Logo";
import {
  CONTACT_EMAIL,
  DELIVERY,
  PRICE_MONTHLY,
  PRICE_UPFRONT,
  SITE_URL,
} from "@/lib/constants";

const PAGE_TITLE = "Terms of Reservation — NOWVA";
const PAGE_DESCRIPTION =
  "What reserving a Nowva Rack means: $0 today, a held place in line, cancel anytime with one email — and what you pay when your rack ships.";

export const metadata: Metadata = {
  title: PAGE_TITLE,
  description: PAGE_DESCRIPTION,
  alternates: {
    canonical: `${SITE_URL}/terms`,
  },
  openGraph: {
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION,
    url: `${SITE_URL}/terms`,
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

export default function TermsPage() {
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
          Terms of Reservation
        </h1>
        <p className="mt-3 font-mono text-[0.68rem] tracking-[0.08em] text-fg-2">
          Last updated July 28, 2026
        </p>

        <p className="mt-8 text-sm leading-relaxed text-fg-2 md:text-base">
          These terms cover reserving the Nowva Rack through this site.
          They&rsquo;re short, because a reservation is a simple thing.
        </p>

        <h2 className={HEADING_CLASS}>What reserving does</h2>
        <p className={BODY_CLASS}>
          A reservation costs $0 and holds your place in line for the founding
          batch. Reservation order determines delivery order. A reservation is
          not a purchase and doesn&rsquo;t commit you to one — we don&rsquo;t
          collect payment details, and nothing is charged.
        </p>

        <h2 className={HEADING_CLASS}>What you&rsquo;ll pay — later</h2>
        <p className={BODY_CLASS}>
          Before your rack ships, we&rsquo;ll ask you to confirm and complete
          your order. The rack is ${PRICE_UPFRONT.toLocaleString("en-US")},
          paid when it ships, and membership is ${PRICE_MONTHLY}/month starting
          after your second month. Until you confirm your order, you owe
          nothing.
        </p>

        <h2 className={HEADING_CLASS}>Delivery</h2>
        <p className={BODY_CLASS}>
          Founding-batch racks are estimated to ship {DELIVERY}. That is an
          estimate, not a guarantee — hardware timelines move, and we&rsquo;ll
          keep reservation holders updated as the build progresses.
        </p>

        <h2 className={HEADING_CLASS}>Cancellation</h2>
        <p className={BODY_CLASS}>
          Cancel anytime by emailing <ContactLink />. One email, no penalty,
          nothing owed. We&rsquo;ll confirm the cancellation and remove your
          reservation.
        </p>

        <h2 className={HEADING_CLASS}>The product is in development</h2>
        <p className={BODY_CLASS}>
          The Nowva Rack is in active development. Product imagery on this site
          shows early CAD renders, and the final design and specifications may
          change before shipping. If something changes materially, you&rsquo;ll
          hear about it in our build updates — and you can always cancel.
        </p>

        <h2 className={HEADING_CLASS}>Your place in line</h2>
        <p className={BODY_CLASS}>
          A reservation is personal to you and can&rsquo;t be sold or
          transferred. If you can no longer take delivery, just cancel — it
          cost you nothing either way.
        </p>

        <h2 className={HEADING_CLASS}>Questions and disputes</h2>
        <p className={BODY_CLASS}>
          Anything unclear, or anything you think we&rsquo;ve gotten wrong —
          email <ContactLink />. A human reads every message.
        </p>
      </main>

      <Footer />
    </div>
  );
}
