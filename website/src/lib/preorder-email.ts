import {
  CONTACT_EMAIL,
  DELIVERY,
  PRICE_MONTHLY,
  PRICE_UPFRONT,
} from "@/lib/constants";

/* The bare apex errors behind Cloudflare — email links use the www host. */
const HOMEPAGE = "https://www.nowvasports.com";

/* Customer-facing reservation confirmation, set in the site's dark
   "night lab" theme. Table layout + inline styles only — Outlook desktop
   renders email with Word's engine, so no flexbox and no CSS gradients
   there; every gradient carries a solid background-color fallback, and
   the web fonts fall back to system stacks where @font-face is ignored. */

const BG = "#09090e";
const CARD_BG = "#121218";
const PANEL_BG = "#1b1b24";
const BORDER = "#26242e";
const BORDER_STRONG = "#363341";
const FG = "#f6f5f8";
const MUTED = "#928fa0";
const FAINT = "#5c5966";
const ACCENT = "#a78bfa";
const ACCENT_INK = "#b8a1ff";
const ON_CTA = "#16131c";
const GRADIENT = "linear-gradient(100deg, #7c3aed 0%, #a78bfa 50%, #d8b4fe 100%)";

const DISPLAY_FONT =
  "'Bricolage Grotesque', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif";
const BODY_FONT =
  "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif";
const MONO_FONT = "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const NEXT_STEPS = [
  {
    title: "Your place is locked",
    body: "Reservation order determines delivery order — you're in line as of today, and it cost you nothing.",
  },
  {
    title: "We build",
    body: "We'll send occasional build updates as the rack moves from CAD to steel — including the parts where hardware gets hard.",
  },
  {
    title: "You confirm before anything ships",
    body: `Before your rack ships (${DELIVERY}), we'll ask you to confirm and complete your order. Until then you owe nothing, and you can cancel anytime.`,
  },
] as const;

export function confirmationSubject(): string {
  return "You're in — your Nowva reservation is confirmed";
}

export function confirmationText(name: string): string {
  return [
    `${name} — you're in.`,
    "",
    "Your founding-batch reservation for the Nowva Rack is confirmed.",
    "",
    ...NEXT_STEPS.flatMap((step, index) => [
      `${index + 1}. ${step.title}`,
      `   ${step.body}`,
      "",
    ]),
    "Your reservation",
    `  Due today:        $0`,
    `  When it ships:    $${PRICE_UPFRONT.toLocaleString("en-US")}`,
    `  Membership:       $${PRICE_MONTHLY}/mo, starting after your second month`,
    `  Delivery:         ${DELIVERY}`,
    "",
    `Questions? Just reply to this email or write to ${CONTACT_EMAIL}.`,
    "",
    "— The Nowva team",
    HOMEPAGE,
  ].join("\n");
}

export function confirmationHtml(name: string): string {
  const safeName = escapeHtml(name);

  const stepsRows = NEXT_STEPS.map(
    (step, index) => `
      <tr>
        <td style="padding:0 0 22px 0;vertical-align:top;width:46px;">
          <span style="display:inline-block;width:28px;height:28px;line-height:28px;text-align:center;border:1px solid ${BORDER_STRONG};border-radius:999px;font-family:${MONO_FONT};font-size:12px;font-weight:600;color:${ACCENT_INK};">${index + 1}</span>
        </td>
        <td style="padding:0 0 22px 0;vertical-align:top;">
          <p style="margin:0 0 5px 0;font-family:${DISPLAY_FONT};font-size:15px;font-weight:700;color:${FG};">${step.title}</p>
          <p style="margin:0;font-family:${BODY_FONT};font-size:14px;line-height:22px;color:${MUTED};">${step.body}</p>
        </td>
      </tr>`,
  ).join("");

  const summaryRow = (label: string, value: string, last = false) => `
      <tr>
        <td style="padding:11px 0;border-bottom:${last ? "none" : `1px solid ${BORDER}`};font-family:${BODY_FONT};font-size:13px;color:${MUTED};">${label}</td>
        <td align="right" style="padding:11px 0;border-bottom:${last ? "none" : `1px solid ${BORDER}`};font-family:${BODY_FONT};font-size:13px;font-weight:700;color:${FG};">${value}</td>
      </tr>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="dark" />
  <meta name="supported-color-schemes" content="dark" />
  <title>Your Nowva reservation is confirmed</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@700;800&family=Plus+Jakarta+Sans:wght@400;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

    /* Progressive enhancement: WebKit clients (Apple Mail, iOS) animate;
       everything else renders the static design. Elements stay visible
       when animation is unsupported — opacity only changes via keyframes. */
    @keyframes np-pan {
      0%, 100% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
    }
    .np-grad {
      background-size: 220% 100% !important;
      animation: np-pan 7s ease-in-out infinite;
    }
    @keyframes np-rise {
      from { opacity: 0; transform: translateY(14px); }
      to { opacity: 1; transform: none; }
    }
    .np-rise-1 { animation: np-rise 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
    .np-rise-2 { animation: np-rise 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.15s both; }
    @media (prefers-reduced-motion: reduce) {
      .np-grad, .np-rise-1, .np-rise-2 { animation: none; }
    }
  </style>
</head>
<body style="margin:0;padding:0;background-color:${BG};">
  <div style="display:none;max-height:0;overflow:hidden;">Your founding-batch reservation for the Nowva Rack is confirmed. $0 today — your place in line is locked.</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="${BG}" style="background-color:${BG};">
    <tr>
      <td align="center" style="padding:44px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;">

          <!-- Logo + wordmark + slogan -->
          <tr>
            <td align="center" class="np-rise-1" style="padding:0 0 30px 0;">
              <img src="${HOMEPAGE}/logo-white.png" width="52" height="52" alt="" style="display:block;margin:0 auto 14px auto;width:52px;height:52px;" />
              <span style="font-family:${DISPLAY_FONT};font-size:15px;font-weight:800;letter-spacing:0.5em;color:${FG};">NOWVA</span>
              <p style="margin:10px 0 0 0;font-family:${MONO_FONT};font-size:10px;font-weight:500;letter-spacing:0.28em;text-transform:uppercase;color:${MUTED};">Train With Intelligence</p>
            </td>
          </tr>

          <!-- Card -->
          <tr>
            <td bgcolor="${CARD_BG}" style="background-color:${CARD_BG};border:1px solid ${BORDER};border-radius:16px;overflow:hidden;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">

                <!-- Violet gradient top rule -->
                <tr>
                  <td height="4" bgcolor="${ACCENT}" class="np-grad" style="background-color:${ACCENT};background-image:${GRADIENT};font-size:0;line-height:0;">&nbsp;</td>
                </tr>

                <tr>
                  <td class="np-rise-2" style="padding:46px 44px 42px 44px;">

                    <p style="margin:0 0 16px 0;font-family:${MONO_FONT};font-size:11px;font-weight:600;letter-spacing:0.22em;text-transform:uppercase;color:${ACCENT_INK};">Reservation confirmed</p>

                    <h1 style="margin:0 0 18px 0;font-family:${DISPLAY_FONT};font-size:31px;line-height:37px;font-weight:800;letter-spacing:-0.02em;color:${FG};">You&rsquo;re in, <span style="color:${ACCENT};">${safeName}</span>.</h1>

                    <p style="margin:0 0 30px 0;font-family:${BODY_FONT};font-size:15px;line-height:24px;color:${MUTED};">Your founding-batch reservation for the <strong style="color:${FG};">Nowva Rack</strong> is confirmed — the first rack that coaches you. Here&rsquo;s what happens from here.</p>

                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      ${stepsRows}
                    </table>

                    <!-- Summary panel -->
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 34px 0;">
                      <tr>
                        <td bgcolor="${PANEL_BG}" style="background-color:${PANEL_BG};border:1px solid ${BORDER};border-radius:12px;padding:20px 24px;">
                          <p style="margin:0 0 6px 0;font-family:${MONO_FONT};font-size:10px;font-weight:600;letter-spacing:0.2em;text-transform:uppercase;color:${FAINT};">Your reservation</p>
                          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                            ${summaryRow("Due today", "$0")}
                            ${summaryRow("When your rack ships", `$${PRICE_UPFRONT.toLocaleString("en-US")}`)}
                            ${summaryRow("Membership", `$${PRICE_MONTHLY}/mo after your second month`)}
                            ${summaryRow("Estimated delivery", DELIVERY, true)}
                          </table>
                        </td>
                      </tr>
                    </table>

                    <!-- CTA: violet gradient key, dark ink — the site's command-key style -->
                    <table role="presentation" cellpadding="0" cellspacing="0">
                      <tr>
                        <td bgcolor="${ACCENT}" class="np-grad" style="background-color:${ACCENT};background-image:${GRADIENT};border-radius:999px;">
                          <a href="${HOMEPAGE}" style="display:inline-block;padding:14px 32px;font-family:${DISPLAY_FONT};font-size:14px;font-weight:700;color:${ON_CTA};text-decoration:none;">See what your coach can do</a>
                        </td>
                      </tr>
                    </table>

                    <p style="margin:34px 0 0 0;font-family:${BODY_FONT};font-size:14px;line-height:22px;color:${MUTED};">Questions, or need to cancel? Just reply to this email — a human reads every message.</p>

                  </td>
                </tr>

                <!-- Hairline + telemetry sign-off -->
                <tr>
                  <td style="padding:0 44px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      <tr><td height="1" style="background-color:${BORDER};font-size:0;line-height:0;">&nbsp;</td></tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:18px 44px 22px 44px;">
                    <p style="margin:0;font-family:${MONO_FONT};font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:${FAINT};">NV-01 &middot; Founding batch &middot; ${DELIVERY}</p>
                  </td>
                </tr>

              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td align="center" style="padding:30px 24px 0 24px;">
              <p style="margin:0 0 6px 0;font-family:${BODY_FONT};font-size:12px;color:${FAINT};">Nowva &middot; The first rack that coaches you</p>
              <p style="margin:0;font-family:${BODY_FONT};font-size:12px;color:${FAINT};">
                <a href="${HOMEPAGE}" style="color:${ACCENT_INK};text-decoration:none;">nowvasports.com</a>
                &nbsp;&middot;&nbsp;
                <a href="mailto:${CONTACT_EMAIL}" style="color:${ACCENT_INK};text-decoration:none;">${CONTACT_EMAIL}</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;
}
