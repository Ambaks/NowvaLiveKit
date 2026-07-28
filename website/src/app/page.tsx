import { Navbar } from "@/components/layout/Navbar";
import { ScrollProgress } from "@/components/layout/ScrollProgress";
import { Footer } from "@/components/layout/Footer";
import { Hero } from "@/components/sections/Hero";
import { Mission } from "@/components/sections/Mission";
import { RackShowcase } from "@/components/sections/RackShowcase";
import { Coach } from "@/components/sections/Coach";
import { OneSet } from "@/components/sections/OneSet";
import { Flywheel } from "@/components/sections/Flywheel";
import { CtaBand } from "@/components/sections/CtaBand";
import { Manifesto } from "@/components/sections/Manifesto";
import { Pricing } from "@/components/sections/Pricing";
import { Faq } from "@/components/sections/Faq";
import { DELIVERY } from "@/lib/constants";

export default function Home() {
  return (
    <div id="top">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <ScrollProgress />
      <Navbar />
      <main id="main">
        <Hero />
        <Mission />
        <RackShowcase />
        <Coach />
        <OneSet />
        <Flywheel />
        <Manifesto />
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
