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
    a: "$2,000 when your rack ships, then $200/month starting after your second month. The membership covers Nova's coaching, programming, and ongoing intelligence updates.",
  },
  {
    q: "There are cameras. What about my privacy?",
    a: "All video is processed on a dedicated AI computer inside the rack. Nothing is uploaded; your footage never leaves the device. There is no cloud video processing, period.",
  },
  {
    q: "Is the design final?",
    a: "No — what you see are early CAD renders and the design is still evolving. What's further along is the intelligence: the biomechanics engine you see in the telemetry above runs today in our lab.",
  },
  {
    q: "What exercises does it coach?",
    a: "The launch focus is the barbell squat — the deepest, most-validated part of our engine — with additional barbell lifts in active development.",
  },
  {
    q: "What do I need at home?",
    a: "A spot for a premium squat rack and a standard outlet. Full dimensions and specs will be published as the design finalizes; reserving costs nothing if it turns out not to fit your space.",
  },
] as const;

export function Faq() {
  return (
    <section id="faq">
      <div className="mx-auto max-w-3xl px-5 py-24 md:px-8 md:py-36">
        <SectionHeading eyebrow="FAQ" title="Fair questions." />

        <Reveal className="mt-12">
          <div className="divide-y divide-border border-y border-border">
            {ITEMS.map((item) => (
              <details key={item.q} className="group py-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-6 [&::-webkit-details-marker]:hidden">
                  <span className="font-display text-base font-bold tracking-tight text-fg md:text-lg">
                    {item.q}
                  </span>
                  <Plus
                    className="size-4 shrink-0 text-fg-3 transition-transform duration-300 group-open:rotate-45 group-open:text-accent-ink"
                    aria-hidden
                  />
                </summary>
                <p className="mt-4 max-w-2xl text-sm leading-relaxed text-fg-2 md:text-base">
                  {item.a}
                </p>
              </details>
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
