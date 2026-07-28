"use client";

import { useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Button } from "@/components/ui/Button";
import { trackEvent } from "@/lib/analytics";
import { CONTACT_EMAIL } from "@/lib/constants";
import { preorderSchema } from "@/lib/validation";

type Status = "idle" | "submitting" | "success" | "error";

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const INPUT_CLASSES =
  "w-full rounded-xl border border-border bg-bg px-4 py-3 text-base text-fg placeholder:text-fg-3 transition-colors duration-200 focus:border-accent focus:outline-none";

export function PreorderForm() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [invalidFields, setInvalidFields] = useState<string[]>([]);
  const successHeadingRef = useRef<HTMLParagraphElement>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "submitting") return;

    const data = new FormData(event.currentTarget);
    const payload = {
      name: String(data.get("name") ?? ""),
      email: String(data.get("email") ?? ""),
      company: String(data.get("company") ?? ""),
    };

    const parsed = preorderSchema.safeParse(payload);
    if (!parsed.success) {
      setInvalidFields(parsed.error.issues.map((issue) => String(issue.path[0])));
      setError(parsed.error.issues[0]?.message ?? "Please check your name and email.");
      return;
    }

    setInvalidFields([]);
    setError(null);
    setStatus("submitting");
    try {
      const res = await fetch("/api/preorder", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      const result = (await res.json().catch(() => null)) as
        | { ok: boolean; error?: string }
        | null;
      if (!res.ok || !result?.ok) {
        throw new Error(result?.error ?? "Request failed");
      }
      setStatus("success");
      trackEvent("generate_lead", { method: "preorder_form" });
    } catch (err) {
      setStatus("error");
      setError(
        err instanceof Error && err.message !== "Request failed"
          ? err.message
          : `Something went wrong on our end. Please try again — or email ${CONTACT_EMAIL}.`,
      );
    }
  }

  return (
    <div className="relative">
      {/* Persistent live region — announces state changes to screen readers. */}
      <p aria-live="polite" className="sr-only">
        {status === "submitting"
          ? "Submitting your reservation."
          : status === "success"
            ? "Reservation confirmed. You're in the founding batch."
            : ""}
      </p>

      <AnimatePresence mode="wait" initial={false}>
        {status === "success" ? (
          <motion.div
            key="success"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EASE }}
            onAnimationComplete={() => successHeadingRef.current?.focus()}
            className="rounded-xl border border-accent/40 bg-accent/10 p-6 text-center"
          >
            <motion.span
              initial={{ scale: 0.4, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.1, ease: EASE }}
              className="mx-auto flex size-12 items-center justify-center rounded-full border border-accent/40 bg-accent/15"
              aria-hidden="true"
            >
              <svg viewBox="0 0 24 24" fill="none" className="size-6 text-accent-ink">
                <motion.path
                  d="M5 12.5 10 17.5 19 7"
                  stroke="currentColor"
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.4, delay: 0.35, ease: EASE }}
                />
              </svg>
            </motion.span>
            <p
              ref={successHeadingRef}
              tabIndex={-1}
              className="mt-4 font-display text-lg font-bold text-fg focus:outline-none"
            >
              You&apos;re in the founding batch.
            </p>
            <p className="mt-2 text-sm leading-relaxed text-fg-2">
              Watch your inbox for build updates from the lab. No payment
              today — we&apos;ll email you before your rack ships to confirm your
              order.
            </p>
          </motion.div>
        ) : (
          <motion.form
            key="form"
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.3 }}
            onSubmit={onSubmit}
            noValidate
            aria-busy={status === "submitting"}
          >
            <div className="space-y-3">
              <label className="block">
                <span className="sr-only">Name</span>
                <input
                  type="text"
                  name="name"
                  autoComplete="name"
                  placeholder="Your name"
                  required
                  aria-invalid={invalidFields.includes("name") || undefined}
                  aria-describedby={
                    invalidFields.includes("name") ? "preorder-error" : undefined
                  }
                  className={INPUT_CLASSES}
                />
              </label>
              <label className="block">
                <span className="sr-only">Email</span>
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  required
                  aria-invalid={invalidFields.includes("email") || undefined}
                  aria-describedby={
                    invalidFields.includes("email") ? "preorder-error" : undefined
                  }
                  className={INPUT_CLASSES}
                />
              </label>
              {/* Honeypot — hidden from humans, irresistible to bots. */}
              <div className="absolute left-[-9999px] top-0" aria-hidden="true">
                <label>
                  Company
                  <input type="text" name="company" tabIndex={-1} autoComplete="off" />
                </label>
              </div>
            </div>

            <AnimatePresence initial={false}>
              {error && (
                <motion.p
                  id="preorder-error"
                  role="alert"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3, ease: EASE }}
                  className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm leading-relaxed text-red-600 dark:text-red-400"
                >
                  {error}
                </motion.p>
              )}
            </AnimatePresence>

            <Button
              type="submit"
              size="lg"
              cta="reserve-form"
              disabled={status === "submitting"}
              className="mt-4 w-full"
            >
              {status === "submitting" ? (
                <>
                  <span
                    className="size-4 animate-spin rounded-full border-2 border-on-cta/30 border-t-on-cta"
                    aria-hidden="true"
                  />
                  Reserving…
                </>
              ) : (
                "Reserve My Spot — $0 Today"
              )}
            </Button>

            <p className="mt-3 text-center text-xs leading-relaxed text-fg-2">
              No payment now. We&apos;ll email you before your rack ships to
              confirm — pay nothing until then. No spam, just build updates.
            </p>
          </motion.form>
        )}
      </AnimatePresence>
    </div>
  );
}
