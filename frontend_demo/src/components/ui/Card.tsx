import { forwardRef } from 'react';
import type { HTMLAttributes } from 'react';
import { cn } from '@/utils/cn';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hoverEffect?: boolean;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, children, hoverEffect = true, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'bg-surface/80 backdrop-blur-sm border border-border rounded-2xl p-6',
          'relative overflow-hidden group',
          hoverEffect && 'hover:border-accent/20 hover:shadow-glow-cyan transition-all duration-300',
          className
        )}
        {...props}
      >
        {/* Gradient overlay on hover */}
        {hoverEffect && (
          <div className="absolute inset-0 bg-gradient-to-br from-accent/[0.03] via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
        )}
        <div className="relative z-10">{children}</div>
      </div>
    );
  }
);

Card.displayName = 'Card';
