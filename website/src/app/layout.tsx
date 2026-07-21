import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans, Syne } from "next/font/google";
import { GoogleAnalytics } from "@next/third-parties/google";
import "./globals.css";
import { IntroLoader } from "@/components/layout/IntroLoader";
import { Providers } from "@/components/layout/Providers";
import { CookieBanner } from "@/components/layout/CookieBanner";
import { DELIVERY, GA_ID, SITE_NAME, SITE_URL } from "@/lib/constants";

const syne = Syne({
  subsets: ["latin"],
  weight: ["700", "800"],
  variable: "--font-syne",
});

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "NOWVA — The AI Personal Trainer, Built Into a Rack",
  description: `The Nowva Rack watches every rep with built-in cameras, diagnoses your form in real time, and coaches you out loud — 100% on-device. Reserve yours for ${DELIVERY}. $0 today.`,
  openGraph: {
    title: "NOWVA — Your Coach. Built Into the Steel.",
    description: `The AI squat rack that sees your form, corrects it in under 50 ms, and never phones home. Reserve yours for ${DELIVERY} — $0 today.`,
    url: SITE_URL,
    siteName: SITE_NAME,
    images: [{ url: "/og.png", width: 1200, height: 630 }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "NOWVA — Your Coach. Built Into the Steel.",
    description: `The AI squat rack that sees your form and corrects it in under 50 ms. Reserve yours for ${DELIVERY} — $0 today.`,
    images: ["/og.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0b",
};

/* Show the intro loader once per tab session; repeats skip it before paint. */
const INTRO_SCRIPT = `try{if(sessionStorage.getItem('nv-intro'))document.documentElement.dataset.intro='off';else sessionStorage.setItem('nv-intro','1')}catch(e){}`;

/* Consent Mode v2: default denied until the cookie banner grants. */
const CONSENT_SCRIPT = `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)};gtag('consent','default',{analytics_storage:'denied',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'});try{if(localStorage.getItem('nv-consent')==='granted')gtag('consent','update',{analytics_storage:'granted'})}catch(e){}`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${syne.variable} ${jakarta.variable} ${jetbrains.variable} antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: INTRO_SCRIPT }} />
        <script dangerouslySetInnerHTML={{ __html: CONSENT_SCRIPT }} />
      </head>
      <body className="min-h-screen font-sans">
        <IntroLoader />
        <Providers>
          {children}
          <CookieBanner />
        </Providers>
      </body>
      <GoogleAnalytics gaId={GA_ID} />
    </html>
  );
}
