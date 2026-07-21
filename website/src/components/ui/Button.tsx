import { cn } from "@/lib/cn";

const VARIANTS = {
  cta: "bg-cta text-on-cta hover:bg-cta-hover shadow-[0_0_0_0_transparent] hover:shadow-[0_8px_40px_-8px_var(--glow-cta)] font-semibold",
  ghost:
    "border border-border-strong text-fg hover:border-accent hover:text-accent-ink bg-transparent",
} as const;

const SIZES = {
  md: "px-5 py-2.5 text-sm",
  lg: "px-7 py-3.5 text-base",
} as const;

type ButtonProps = {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
  href?: string;
  className?: string;
  children: React.ReactNode;
  /** Analytics label; a delegated listener fires cta_click with it. */
  cta?: string;
  type?: "button" | "submit";
  disabled?: boolean;
};

export function Button({
  variant = "cta",
  size = "md",
  href,
  className,
  children,
  cta,
  type = "button",
  disabled,
}: ButtonProps) {
  const classes = cn(
    "inline-flex items-center justify-center gap-2 rounded-full tracking-tight",
    "transition-all duration-300 active:scale-[0.97] disabled:opacity-60 disabled:pointer-events-none",
    VARIANTS[variant],
    SIZES[size],
    className,
  );
  if (href) {
    return (
      <a href={href} className={classes} data-cta={cta}>
        {children}
      </a>
    );
  }
  return (
    <button type={type} className={classes} data-cta={cta} disabled={disabled}>
      {children}
    </button>
  );
}
