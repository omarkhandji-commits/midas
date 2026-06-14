import { cva, type VariantProps } from "class-variance-authority";

// Extracted from button.tsx so the component file exports components only — keeps
// react-refresh happy and matches the canonical shadcn split pattern.
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-semibold " +
    "border transition-colors disabled:pointer-events-none disabled:opacity-50 " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
    "focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
  {
    variants: {
      variant: {
        default: "border-ink bg-transparent text-ink hover:bg-ink hover:text-paper",
        primary:
          "border-accent bg-accent text-paper hover:bg-accent-hi hover:border-accent-hi",
        ok: "border-accent text-accent hover:bg-accent hover:text-paper",
        no: "border-warn text-warn hover:bg-warn hover:text-paper",
        ghost: "border-transparent text-ink hover:bg-rule-soft",
        link: "border-transparent text-accent underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-4",
        lg: "h-10 px-5 text-[15px]",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export type ButtonVariantProps = VariantProps<typeof buttonVariants>;
