import { ThemedLogo } from "@/components/ui/Logo";
import { CONTACT_EMAIL } from "@/lib/constants";

const COLUMNS = [
  {
    title: "Product",
    links: [
      { label: "The Rack", href: "#rack" },
      { label: "The Coach", href: "#coach" },
      { label: "Technology", href: "#technology" },
      { label: "FAQ", href: "#faq" },
      { label: "Reserve", href: "#reserve" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Mission", href: "#mission" },
      { label: "Contact", href: `mailto:${CONTACT_EMAIL}` },
      {
        label: "Work with us",
        href: `mailto:${CONTACT_EMAIL}?subject=Working%20at%20Nowva`,
      },
    ],
  },
] as const;

export function Footer() {
  return (
    <footer className="relative overflow-hidden bg-bg-2">
      {/* Hairline that blends from the standard border into a violet glow at center. */}
      <div
        aria-hidden
        className="h-px w-full bg-linear-to-r from-border via-accent/60 to-border"
      />

      <div className="mx-auto max-w-6xl px-5 pt-16 md:px-8">
        <div className="flex flex-col gap-12 md:flex-row md:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-3">
              <ThemedLogo size={30} />
              <span className="font-display text-base font-extrabold tracking-[0.3em] text-fg">
                NOWVA
              </span>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-fg-2">
              A full coach, built into the steel.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-12 sm:grid-cols-3">
            {COLUMNS.map((column) => (
              <div key={column.title}>
                <p className="eyebrow">{column.title}</p>
                <ul className="mt-4 space-y-3">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-sm text-fg-2 transition-colors duration-200 hover:text-accent-ink"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <div>
              <p className="eyebrow">Reservation terms</p>
              <p className="mt-4 max-w-[16rem] text-sm leading-relaxed text-fg-2">
                Reserving is free and holds your place in line. No payment
                until your rack ships — cancel anytime with one email to{" "}
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="text-accent-ink underline decoration-accent-ink/30 underline-offset-2 transition-colors duration-200 hover:text-accent-strong hover:decoration-accent-strong/60"
                >
                  {CONTACT_EMAIL}
                </a>
                .
              </p>
            </div>
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-3 border-t border-border pt-8 md:flex-row md:items-baseline md:justify-between">
          <p className="shrink-0 font-mono text-[0.68rem] tracking-[0.08em] text-fg-2">
            © 2026 Nowva. All rights reserved.
          </p>
          <p className="max-w-lg font-mono text-[0.68rem] leading-relaxed tracking-[0.02em] text-fg-2 md:text-right">
            The Nowva Rack is in development. Product imagery shows early CAD
            renders; final design and specifications may change.
          </p>
        </div>
      </div>

      {/* Oversized wordmark, clipped at the page's bottom edge. Decorative only. */}
      <div aria-hidden className="pointer-events-none mt-10 select-none">
        <p className="translate-y-[0.3em] pl-[0.16em] text-center font-display text-[clamp(4.5rem,15vw,11.5rem)] font-extrabold leading-none tracking-[0.16em] text-fg/5">
          NOWVA
        </p>
      </div>
    </footer>
  );
}
