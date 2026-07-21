import { z } from "zod";

export const preorderSchema = z.object({
  name: z.string().trim().min(1, "Please tell us your name").max(100),
  email: z.string().trim().email("That email doesn't look right").max(254),
  /** Honeypot — humans never see this field. Any value is accepted by the
      schema; the API route quietly drops submissions that filled it. */
  company: z.string().optional(),
});

export type PreorderInput = z.infer<typeof preorderSchema>;
