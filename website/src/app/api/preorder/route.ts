import { NextRequest, NextResponse } from "next/server";
import { Resend } from "resend";
import { preorderSchema } from "@/lib/validation";
import { CONTACT_EMAIL } from "@/lib/constants";

const WINDOW_MS = 10 * 60 * 1000;
const MAX_PER_WINDOW = 5;
const MAX_TRACKED_IPS = 1000;

/* Per-instance rate limit — good enough for a launch page. */
const hits = new Map<string, number[]>();

function rateLimited(ip: string): boolean {
  const now = Date.now();
  if (hits.size > MAX_TRACKED_IPS) {
    for (const [key, stamps] of hits) {
      if (now - (stamps[stamps.length - 1] ?? 0) > WINDOW_MS) hits.delete(key);
    }
  }
  const recent = (hits.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  recent.push(now);
  hits.set(ip, recent);
  return recent.length > MAX_PER_WINDOW;
}

function clientIp(request: NextRequest): string {
  const real = request.headers.get("x-real-ip");
  if (real) return real.trim();
  /* Rightmost x-forwarded-for entry is the one our own proxy appended —
     leftmost entries are client-controlled and spoofable. */
  const forwarded = request.headers.get("x-forwarded-for");
  if (!forwarded) return "unknown";
  const parts = forwarded.split(",");
  return parts[parts.length - 1].trim();
}

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid request" }, { status: 400 });
  }

  const parsed = preorderSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: "Please check your name and email." },
      { status: 400 },
    );
  }
  const { name, email, company } = parsed.data;

  /* Filled honeypot → bots get a quiet 200, never a tip-off. */
  if (company && company.length > 0) {
    return NextResponse.json({ ok: true });
  }

  if (rateLimited(clientIp(request))) {
    return NextResponse.json(
      { ok: false, error: "Too many requests — please try again in a few minutes." },
      { status: 429 },
    );
  }

  if (process.env.PREORDER_DRY_RUN === "1") {
    console.log("[preorder:dry-run]", { name, email });
    return NextResponse.json({ ok: true });
  }

  const apiKey = process.env.RESEND_API_KEY;
  if (!apiKey) {
    console.error("[preorder] RESEND_API_KEY is not set");
    return NextResponse.json(
      { ok: false, error: "Reservations are briefly offline. Please email us instead." },
      { status: 500 },
    );
  }

  try {
    const resend = new Resend(apiKey);
    const { error } = await resend.emails.send({
      from: "Nowva Preorders <preorders@nowva.ai>",
      to: process.env.PREORDER_TO ?? CONTACT_EMAIL,
      replyTo: email,
      subject: `New preorder reservation — ${name}`,
      text: [
        "New founding-batch reservation",
        "",
        `Name:  ${name}`,
        `Email: ${email}`,
        `Time:  ${new Date().toISOString()}`,
      ].join("\n"),
    });
    if (error) throw new Error(error.message);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[preorder] send failed:", err);
    return NextResponse.json(
      { ok: false, error: "We couldn't save your reservation. Please try again." },
      { status: 500 },
    );
  }
}
