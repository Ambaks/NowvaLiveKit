import { cn } from "@/lib/cn";

const CORNERS = [
  "top-0 left-0 border-t border-l",
  "top-0 right-0 border-t border-r",
  "bottom-0 left-0 border-b border-l",
  "bottom-0 right-0 border-b border-r",
] as const;

/* CV-viewfinder frame: four corner brackets and an optional mono label,
   echoing the camera-calibration overlay in the real pipeline. */
export function Viewfinder({
  children,
  label,
  className,
}: {
  children: React.ReactNode;
  label?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      {CORNERS.map((corner) => (
        <span
          key={corner}
          aria-hidden
          className={cn("absolute z-10 size-5 border-accent/70", corner)}
        />
      ))}
      {label && (
        <span className="absolute left-5 top-4 z-10 font-mono text-[0.65rem] tracking-[0.22em] text-accent-ink/90">
          {label}
        </span>
      )}
      {children}
    </div>
  );
}
