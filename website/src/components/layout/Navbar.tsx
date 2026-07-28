"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Menu, X } from "lucide-react";
import { ThemedLogo } from "@/components/ui/Logo";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { NAV_LINKS } from "@/lib/constants";
import { cn } from "@/lib/cn";

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

export function Navbar() {
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let lastY = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      setScrolled(y > 24);
      setHidden(y > 140 && y > lastY);
      lastY = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  /* Lock page scroll while the menu is open — same <html> overflow approach
     the 3D intro uses. */
  useEffect(() => {
    if (!menuOpen) return;
    const html = document.documentElement;
    const previousOverflow = html.style.overflow;
    html.style.overflow = "hidden";
    return () => {
      html.style.overflow = previousOverflow;
    };
  }, [menuOpen]);

  /* The open menu presents as modal, so inert the covered page regions —
     same element.inert approach the 3D intro uses — to keep Tab and
     keyboard scrolling out of the page behind the backdrop. */
  useEffect(() => {
    if (!menuOpen) return;
    const covered = [
      document.getElementById("main"),
      document.querySelector("footer"),
    ].filter(
      (region): region is HTMLElement =>
        region instanceof HTMLElement && !region.inert,
    );
    for (const region of covered) region.inert = true;
    return () => {
      for (const region of covered) region.inert = false;
    };
  }, [menuOpen]);

  /* Escape closes and hands focus back to the trigger; crossing into the
     md+ layout closes the same way so the scroll lock can't outlive the
     hamburger. */
  useEffect(() => {
    if (!menuOpen) return;
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      menuButtonRef.current?.focus();
    };
    const mdQuery = window.matchMedia("(min-width: 768px)");
    const onMdChange = () => {
      if (!mdQuery.matches) return;
      setMenuOpen(false);
      menuButtonRef.current?.focus();
    };
    window.addEventListener("keydown", onKeydown);
    mdQuery.addEventListener("change", onMdChange);
    return () => {
      window.removeEventListener("keydown", onKeydown);
      mdQuery.removeEventListener("change", onMdChange);
    };
  }, [menuOpen]);

  /* Delegated close: any anchor tap while the menu is open — menu link,
     bar CTA, or logo — dismisses the menu. Unlock scroll synchronously so
     the anchor's smooth scroll starts before React re-renders and the
     effect cleanup runs. */
  const onNavClick = (event: React.MouseEvent<HTMLElement>) => {
    if (!(event.target as HTMLElement).closest("a")) return;
    document.documentElement.style.overflow = "";
    setMenuOpen(false);
  };

  return (
    <header
      inert={hidden && !menuOpen}
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-transform duration-500 ease-out",
        hidden && !menuOpen && "-translate-y-full",
      )}
    >
      <div
        className={cn(
          "border-b transition-[background-color,border-color,box-shadow] duration-500",
          scrolled || menuOpen
            ? "border-[color-mix(in_oklab,var(--accent)_20%,var(--border))] bg-bg/80 shadow-[0_12px_40px_-24px_var(--glow)] backdrop-blur-xl"
            : "border-transparent bg-transparent",
        )}
      >
        <nav
          onClick={menuOpen ? onNavClick : undefined}
          className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 md:px-8"
        >
          <a href="#top" className="group flex items-center gap-3" aria-label="NOWVA — back to top">
            <ThemedLogo
              size={26}
              className="transition-[filter] duration-300 group-hover:drop-shadow-[0_0_9px_color-mix(in_oklab,var(--accent)_50%,transparent)]"
            />
            <span className="font-display text-sm font-extrabold tracking-[0.3em] text-fg">
              NOWVA
            </span>
          </a>

          <div className="hidden items-center gap-8 md:flex">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="group relative text-sm text-fg-2 transition-colors duration-200 hover:text-fg"
              >
                {link.label}
                <span
                  aria-hidden
                  className="absolute inset-x-0 -bottom-1 h-px origin-left scale-x-0 bg-accent-ink transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-x-100"
                />
              </a>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Button href="#reserve" size="md" cta="navbar">
              <span className="whitespace-nowrap">
                Reserve<span className="hidden sm:inline"> — $0 today</span>
              </span>
            </Button>
            {/* Invisible after-overlay expands the 36px circle to a 44px
                touch target, matching the intro skip button's pattern. */}
            <button
              ref={menuButtonRef}
              type="button"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls="mobile-menu"
              onClick={() => setMenuOpen((prev) => !prev)}
              className="relative inline-flex size-9 items-center justify-center rounded-full border border-border text-fg-2 transition-colors duration-300 after:absolute after:-inset-1 after:content-[''] hover:border-accent hover:text-accent-ink md:hidden"
            >
              {menuOpen ? <X className="size-4" /> : <Menu className="size-4" />}
            </button>
          </div>

          <AnimatePresence>
            {menuOpen && (
              <motion.div
                key="backdrop"
                aria-hidden
                onClick={() => {
                  setMenuOpen(false);
                  menuButtonRef.current?.focus();
                }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className="fixed inset-x-0 top-0 -z-10 h-svh bg-bg/60 md:hidden"
              />
            )}
            {menuOpen && (
              <motion.div
                key="menu"
                id="mobile-menu"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.35, ease: EASE }}
                className="absolute inset-x-0 top-full max-h-[calc(100svh-4rem)] overflow-y-auto overscroll-contain border-b border-[color-mix(in_oklab,var(--accent)_20%,var(--border))] bg-bg/80 shadow-[0_24px_60px_-32px_var(--glow)] backdrop-blur-xl md:hidden"
              >
                <div className="flex flex-col px-5 pb-6 pt-1">
                  {NAV_LINKS.map((link) => (
                    <a
                      key={link.href}
                      href={link.href}
                      className="border-b border-border py-3.5 text-base text-fg-2 transition-colors duration-200 hover:text-fg"
                    >
                      {link.label}
                    </a>
                  ))}
                  <Button href="#reserve" size="md" cta="mobile-menu" className="mt-5 w-full">
                    <span className="whitespace-nowrap">Reserve — $0 today</span>
                  </Button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </nav>
      </div>
    </header>
  );
}
