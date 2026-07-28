"use client";

import { useEffect, useState } from "react";
import { ThemedLogo } from "@/components/ui/Logo";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { NAV_LINKS } from "@/lib/constants";
import { cn } from "@/lib/cn";

export function Navbar() {
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);

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

  return (
    <header
      inert={hidden}
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-transform duration-500 ease-out",
        hidden && "-translate-y-full",
      )}
    >
      <div
        className={cn(
          "border-b transition-[background-color,border-color,box-shadow] duration-500",
          scrolled
            ? "border-[color-mix(in_oklab,var(--accent)_20%,var(--border))] bg-bg/80 shadow-[0_12px_40px_-24px_var(--glow)] backdrop-blur-xl"
            : "border-transparent bg-transparent",
        )}
      >
        <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 md:px-8">
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
          </div>
        </nav>
      </div>
    </header>
  );
}
