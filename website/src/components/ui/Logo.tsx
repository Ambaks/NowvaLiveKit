import Image from "next/image";
import { cn } from "@/lib/cn";

/* The W monogram, swapping white/black marks with the theme. */
export function ThemedLogo({ size, className }: { size: number; className?: string }) {
  return (
    <span className={cn("inline-flex", className)}>
      <Image
        src="/logo-white.png"
        alt=""
        width={size}
        height={size}
        className="hidden dark:block"
      />
      <Image
        src="/logo-black.png"
        alt=""
        width={size}
        height={size}
        className="dark:hidden"
      />
    </span>
  );
}
