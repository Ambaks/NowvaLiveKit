"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { trackEvent } from "@/lib/analytics";
import { CONTACT_EMAIL } from "@/lib/constants";
import { preorderSchema } from "@/lib/validation";

type Status = "idle" | "submitting" | "success" | "error";

const INPUT_CLASSES =
  "w-full rounded-xl border border-border bg-bg px-4 py-3 text-sm text-fg placeholder:text-fg-3 transition-colors duration-200 focus:border-accent focus:outline-none";

export function PreorderForm() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

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
      setError(parsed.error.issues[0]?.message ?? "Please check your name and email.");
      return;
    }

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
      <AnimatePresence mode="wait" initial={false}>
        {status === "success" ? (
          <motion.div
            key="success"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="rounded-xl border border-accent/40 bg-accent/10 p-6 text-center"
          >
            <p className="font-display text-lg font-bold text-fg">
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

            {error && (
              <p role="alert" className="mt-3 text-sm text-red-500">
                {error}
              </p>
            )}

            <Button
              type="submit"
              size="lg"
              cta="reserve-form"
              disabled={status === "submitting"}
              className="mt-4 w-full"
            >
              {status === "submitting" && (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              )}
              {status === "submitting" ? "Reserving…" : "Reserve My Spot — $0 Today"}
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
