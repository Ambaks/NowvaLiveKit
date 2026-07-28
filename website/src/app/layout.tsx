import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import { GoogleAnalytics } from "@next/third-parties/google";
import "./globals.css";
import { IntroLoader } from "@/components/layout/IntroLoader";
import { IntroStage } from "@/components/intro/IntroStage";
import { Providers } from "@/components/layout/Providers";
import { CookieBanner } from "@/components/layout/CookieBanner";
import {
  CONTACT_EMAIL,
  GA_ID,
  PRICE_MONTHLY,
  PRICE_UPFRONT,
  SITE_NAME,
  SITE_URL,
} from "@/lib/constants";

const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
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
  title: "NOWVA — The First Rack That Coaches You",
  description:
    "Cameras in the steel. An AI coach that corrects your form rep by rep, programs your training, and plans your nutrition — 100% on-device. Reserve for $0.",
  alternates: {
    canonical: SITE_URL,
  },
  openGraph: {
    title: "NOWVA — The First Rack That Coaches You",
    description:
      "The AI rack that sees your form, catches faults in under 50 ms, and coaches your whole training — programming, nutrition, progress. Never phones home. Reserve yours — $0 today.",
    url: SITE_URL,
    siteName: SITE_NAME,
    images: [{ url: "/og.png", width: 1200, height: 630 }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "NOWVA — The First Rack That Coaches You",
    description:
      "The AI rack that sees your form, catches faults in under 50 ms, and coaches your whole training. Reserve yours — $0 today.",
    images: ["/og.png"],
  },
};

/* The site theme is class-driven and defaults to dark regardless of OS
   preference, so a media-keyed themeColor would mismatch on light-OS
   first visits. */
export const viewport: Viewport = {
  themeColor: "#09090e",
};

/* Organization + Product structured data for search engines. */
const JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: SITE_NAME,
      url: SITE_URL,
      logo: `${SITE_URL}/logo-black.png`,
      email: CONTACT_EMAIL,
    },
    {
      "@type": "Product",
      name: "Nowva Rack",
      description:
        "The AI power rack that corrects your form rep by rep, programs your training, and plans your nutrition — 100% on-device.",
      image: `${SITE_URL}/og.png`,
      brand: { "@type": "Brand", name: SITE_NAME },
      offers: {
        "@type": "Offer",
        price: PRICE_UPFRONT,
        priceCurrency: "USD",
        availability: "https://schema.org/PreOrder",
        url: `${SITE_URL}/#reserve`,
        description: `$${PRICE_UPFRONT.toLocaleString("en-US")} when your rack ships, then $${PRICE_MONTHLY}/month starting after your second month. Reservation is free.`,
      },
    },
  ],
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
      className={`${bricolage.variable} ${jakarta.variable} ${jetbrains.variable} antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: INTRO_SCRIPT }} />
        <script dangerouslySetInnerHTML={{ __html: CONSENT_SCRIPT }} />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(JSON_LD).replace(/</g, "\\u003c"),
          }}
        />
      </head>
      <body className="min-h-screen font-sans">
        <IntroLoader />
        <IntroStage />
        <Providers>
          {children}
          <CookieBanner />
        </Providers>
      </body>
      <GoogleAnalytics gaId={GA_ID} />
    </html>
  );
}
