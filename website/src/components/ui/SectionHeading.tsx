import { cn } from "@/lib/cn";
import { Reveal } from "@/components/ui/Reveal";

export function SectionHeading({
  eyebrow,
  title,
  lead,
  align = "left",
  className,
}: {
  eyebrow: string;
  title: React.ReactNode;
  lead?: React.ReactNode;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <Reveal
      className={cn(
        "max-w-3xl",
        align === "center" && "mx-auto text-center",
        className,
      )}
    >
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="mt-4 font-display text-4xl font-extrabold leading-[1.05] tracking-tight text-fg md:text-5xl">
        {title}
      </h2>
      {lead && (
        <p className="mt-5 text-lg leading-relaxed text-fg-2">{lead}</p>
      )}
    </Reveal>
  );
}
