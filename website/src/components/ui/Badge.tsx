import { cn } from "@/lib/cn";

export function Badge({
  children,
  pulse = false,
  className,
}: {
  children: React.ReactNode;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "eyebrow inline-flex items-center gap-2.5 rounded-full border border-border px-4 py-2",
        className,
      )}
    >
      {pulse && (
        <span className="pulse-dot size-1.5 rounded-full bg-accent" aria-hidden />
      )}
      {children}
    </span>
  );
}
