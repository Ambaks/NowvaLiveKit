import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { Hero } from "@/components/sections/Hero";
import { Problem } from "@/components/sections/Problem";
import { RackShowcase } from "@/components/sections/RackShowcase";
import { OneSet } from "@/components/sections/OneSet";
import { TechProof } from "@/components/sections/TechProof";
import { CtaBand } from "@/components/sections/CtaBand";
import { Mission } from "@/components/sections/Mission";
import { Pricing } from "@/components/sections/Pricing";
import { Faq } from "@/components/sections/Faq";
import { DELIVERY } from "@/lib/constants";

export default function Home() {
  return (
    <div id="top">
      <Navbar />
      <main>
        <Hero />
        <Problem />
        <RackShowcase />
        <OneSet />
        <TechProof />
        <CtaBand
          headline="Convinced by the telemetry?"
          sub="The founding batch is open"
          location="tech-band"
        />
        <Mission />
        <Pricing />
        <Faq />
        <CtaBand
          headline={
            <>
              Train with <span className="gradient-text">intelligence.</span>
            </>
          }
          sub={`Founding batch · ${DELIVERY} · $0 to reserve`}
          location="final-band"
        />
      </main>
      <Footer />
    </div>
  );
}
