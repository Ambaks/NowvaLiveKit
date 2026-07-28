"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CONTACT_EMAIL, DELIVERY } from "@/lib/constants";

const ITEMS = [
  {
    q: "When does it ship?",
    a: `First founding-batch racks ship ${DELIVERY}. Reservation order determines delivery order. We'll send build updates along the way — including the moments where hardware gets hard.`,
  },
  {
    q: "What does reserving actually commit me to?",
    a: `Nothing. A reservation is free and holds your place in line. Before your rack ships we'll ask you to confirm and complete your order; until then you owe nothing, and you can cancel anytime by emailing ${CONTACT_EMAIL}.`,
  },
  {
    q: "What do I pay, and when?",
    a: "$2,000 when your rack ships, then $200/month starting after your second month. The membership covers Nova's live coaching, training programming, nutrition, progress analytics, and new movements as they ship — for everyone in your household.",
  },
  {
    q: "What happens if I stop paying?",
    a: `The rack remains a premium power rack and your training history stays yours. Live coaching, programming, nutrition, and updates pause until you restart — one email to ${CONTACT_EMAIL}, no penalty, no lock-in.`,
  },
  {
    q: "How is this different from Tonal or Tempo?",
    a: "Tonal swaps the barbell for cables. Tempo pointed a camera at dumbbells — the right instinct, a generation too early. Neither coaches heavy barbell training in a power rack. Nowva does: it reconstructs your body in 3D from multiple cameras, diagnoses faults against your own anatomy mid-rep, and speaks the correction before your next rep — then programs your training and your nutrition around what it saw. Nothing on the market watches a loaded barbell the way a coach does.",
  },
  {
    q: "I've never touched a barbell. Is this for me?",
    a: "Especially you. Coaching matters most when you're learning — that's when technique gets set and bad habits start. Nova teaches every movement from your first rep, in plain language, and starts your program at your level — empty bar included. You don't need to know what you're doing. That's Nova's job.",
  },
  {
    q: "Why hasn't this existed before?",
    a: "Because it just became possible. Real-time 3D biomechanics used to require a lab and a server rack. Edge AI chips can now run that workload inside a piece of gym equipment — no cloud, no latency, no subscription to someone else's data center. The hardware finally caught up to the idea.",
  },
  {
    q: "How does it get smarter over time?",
    a: "Every cue Nova gives is scored against what happens on your next rep — did the fault shrink, did the score climb. Multiplied across every rack, that teaches Nowva which cue fixes which fault for which body, and the lessons ship back to every coach as updates. A coach that grades its own coaching — that data exists nowhere else.",
  },
  {
    q: "There are cameras. What about my privacy?",
    a: "All video is processed on a dedicated AI computer inside the rack — your footage never leaves the device, and there is no cloud video processing, period. What makes the fleet smarter is anonymized math: joint angles, fault severities, cue outcomes. Numbers, never video.",
  },
  {
    q: "Is the design final?",
    a: "No — what you see are early CAD renders and the design is still evolving. What's further along is the intelligence: the biomechanics engine runs today in our lab, live on the barbell squat.",
  },
  {
    q: "What exercises does it coach?",
    a: "The goal is your entire program. We proved the engine on the barbell squat — the lift we've validated most deeply — and the other big lifts come next on the same stack, with dumbbell and accessory work behind them. Every new movement ships to every rack as a software update; you never buy new hardware to get more coach.",
  },
  {
    q: "Programming and nutrition too — really?",
    a: "Yes. Form correction is the part only Nowva can do, but coaching is the whole job: Nova builds your training plan from measured performance — loads, sets, progressions — and sets calorie and protein targets matched to your goal. Both adapt as your numbers move.",
  },
  {
    q: "What do I need at home?",
    a: "A spot for a full power rack and a standard outlet. Full dimensions and specs will be published as the design finalizes; reserving costs nothing if it turns out not to fit your space.",
  },
] as const;

function FaqItem({
  question,
  answer,
  panelId,
}: {
  question: string;
  answer: string;
  panelId: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-border transition-colors duration-300 hover:border-accent/40">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((prev) => !prev)}
        className="group flex w-full cursor-pointer items-center justify-between gap-6 py-5 text-left"
      >
        <span
          className={`font-display text-base font-bold tracking-tight transition-colors duration-300 md:text-lg ${
            open ? "text-accent-ink" : "text-fg group-hover:text-accent-ink"
          }`}
        >
          {question}
        </span>
        <Plus
          className={`size-4 shrink-0 transition-[transform,color] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none ${
            open
              ? "rotate-45 text-accent-ink"
              : "text-fg-3 group-hover:text-accent-ink"
          }`}
          aria-hidden
        />
      </button>
      <div
        id={panelId}
        aria-hidden={!open}
        className={`grid transition-[grid-template-rows] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none ${
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        }`}
      >
        <div className="overflow-hidden">
          <p
            className={`max-w-2xl pb-5 text-sm leading-relaxed text-fg-2 transition-opacity duration-500 motion-reduce:transition-none md:text-base ${
              open ? "opacity-100" : "opacity-0"
            }`}
          >
            {answer}
          </p>
        </div>
      </div>
    </div>
  );
}

export function Faq() {
  return (
    <section id="faq">
      <div className="mx-auto max-w-3xl px-5 py-24 md:px-8 md:py-36">
        <SectionHeading eyebrow="FAQ" title="Fair questions." />

        <Reveal className="mt-12">
          <div className="border-t border-border">
            {ITEMS.map((item, index) => (
              <FaqItem
                key={item.q}
                question={item.q}
                answer={item.a}
                panelId={`faq-panel-${index}`}
              />
            ))}
          </div>
          <p className="mt-8 text-sm text-fg-2">
            Still thinking?{" "}
            <a
              href="#reserve"
              data-cta="faq"
              className="text-accent-ink underline underline-offset-2 transition-opacity hover:opacity-75"
            >
              Reserving is free →
            </a>
          </p>
        </Reveal>
      </div>
    </section>
  );
}
