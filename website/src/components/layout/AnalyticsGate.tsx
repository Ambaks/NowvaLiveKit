"use client";

import { useSyncExternalStore } from "react";
import { GoogleAnalytics } from "@next/third-parties/google";
import { GA_ID } from "@/lib/constants";

const subscribe = (onChange: () => void) => {
  window.addEventListener("nv:consent", onChange);
  return () => window.removeEventListener("nv:consent", onChange);
};

const readGranted = () => {
  try {
    return localStorage.getItem("nv-consent") === "granted";
  } catch {
    return false;
  }
};

/* Basic consent mode: gtag.js is not loaded at all until the visitor grants
   analytics — before that the browser never contacts Google, which is what
   the privacy policy promises. updateConsent() dispatches "nv:consent" so a
   mid-session Allow mounts the script immediately. */
export function AnalyticsGate() {
  const granted = useSyncExternalStore(subscribe, readGranted, () => false);
  return granted ? <GoogleAnalytics gaId={GA_ID} /> : null;
}
