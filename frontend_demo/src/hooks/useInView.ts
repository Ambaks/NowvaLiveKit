import { useEffect, useState, type RefObject } from 'react';

interface UseInViewOptions {
  once?: boolean;
  amount?: number; // 0 to 1 (percentage of element visible)
}

export function useInView(
  ref: RefObject<HTMLElement | null>,
  options: UseInViewOptions = {}
): boolean {
  const { once = true, amount = 0.2 } = options;
  const [isInView, setIsInView] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true);
          if (once) {
            observer.unobserve(element);
          }
        } else if (!once) {
          setIsInView(false);
        }
      },
      { threshold: amount }
    );

    observer.observe(element);

    return () => {
      observer.unobserve(element);
    };
  }, [ref, once, amount]);

  return isInView;
}
