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
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-transform duration-500 ease-out",
        hidden && "-translate-y-full",
      )}
    >
      <div
        className={cn(
          "border-b transition-colors duration-500",
          scrolled
            ? "border-border bg-bg/80 backdrop-blur-xl"
            : "border-transparent bg-transparent",
        )}
      >
        <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 md:px-8">
          <a href="#top" className="flex items-center gap-3" aria-label="NOWVA — back to top">
            <ThemedLogo size={26} />
            <span className="font-display text-sm font-extrabold tracking-[0.3em] text-fg">
              NOWVA
            </span>
          </a>

          <div className="hidden items-center gap-8 md:flex">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm text-fg-2 transition-colors duration-200 hover:text-fg"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Button href="#reserve" size="md" cta="navbar">
              Reserve — $0 today
            </Button>
          </div>
        </nav>
      </div>
    </header>
  );
}
