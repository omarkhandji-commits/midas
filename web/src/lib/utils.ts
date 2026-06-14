import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Tailwind-aware classname merger. Used by every shadcn-style component.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
