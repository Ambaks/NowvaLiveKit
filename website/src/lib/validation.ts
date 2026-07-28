import { z } from "zod";

export const preorderSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Please tell us your name")
    .max(100)
    /* No CR/LF or other control characters — the name is interpolated
       into an email subject header. */
    .regex(/^[^\u0000-\u001f\u007f]+$/, "Please tell us your name"),
  email: z.string().trim().email("That email doesn't look right").max(254),
  /** Honeypot — humans never see this field. The API route quietly drops
      submissions that filled it; the cap just bounds bot payloads. */
  company: z.string().max(200).optional(),
});

export type PreorderInput = z.infer<typeof preorderSchema>;
