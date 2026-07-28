"use client";

/* Site-wide error boundary: a branded recovery screen instead of Next's
   default "Application error" page when a client-side exception escapes. */

import { useEffect } from "react";

export default function Error({
  error,
}: {
  error: Error & { digest?: string };
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="font-display text-3xl font-extrabold tracking-tight text-fg">
        Something went wrong
      </h1>
      <p className="max-w-md text-fg-2">
        An unexpected error interrupted the page. Reloading usually fixes it.
      </p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="inline-flex items-center justify-center rounded-full border border-border-strong bg-transparent px-5 py-2.5 text-sm tracking-tight text-fg transition-all duration-300 hover:border-accent hover:text-accent-ink active:scale-[0.97]"
      >
        Reload page
      </button>
    </main>
  );
}
