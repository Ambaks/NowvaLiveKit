import { ThemedLogo } from "@/components/ui/Logo";
import { CONTACT_EMAIL } from "@/lib/constants";

const COLUMNS = [
  {
    title: "Product",
    links: [
      { label: "The Rack", href: "#rack" },
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
    <footer className="border-t border-border bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-16 md:px-8">
        <div className="flex flex-col gap-12 md:flex-row md:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-3">
              <ThemedLogo size={30} />
              <span className="font-display text-base font-extrabold tracking-[0.3em] text-fg">
                NOWVA
              </span>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-fg-2">
              Precision intelligence for human performance.
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
                        className="text-sm text-fg-2 transition-colors duration-200 hover:text-fg"
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
                  className="text-accent-ink underline underline-offset-2"
                >
                  {CONTACT_EMAIL}
                </a>
                .
              </p>
            </div>
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-3 border-t border-border pt-8 md:flex-row md:items-center md:justify-between">
          <p className="text-xs text-fg-2">© 2026 Nowva. All rights reserved.</p>
          <p className="font-mono text-[0.68rem] leading-relaxed text-fg-2">
            The Nowva Rack is in development. Product imagery shows early CAD
            renders; final design and specifications may change.
          </p>
        </div>
      </div>
    </footer>
  );
}
