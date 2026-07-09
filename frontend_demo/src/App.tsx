import { Navbar } from '@/components/sections/Navbar';
import { Hero } from '@/components/sections/Hero';
import { SocialProof } from '@/components/sections/SocialProof';
import { HowItWorks } from '@/components/sections/HowItWorks';
import { ProductFeatures } from '@/components/sections/ProductFeatures';
import { ProductShowcase } from '@/components/sections/ProductShowcase';
import { SampleProgram } from '@/components/sections/SampleProgram';
import { FinalCTA } from '@/components/sections/FinalCTA';
import { ProgramGenerator } from '@/components/sections/ProgramGenerator';
import { Footer } from '@/components/sections/Footer';
import { CookieBanner } from '@/components/CookieBanner';

function App() {
  return (
    <div className="min-h-screen bg-background">
      <a
        href="#program-generator"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-cta focus:text-background focus:font-semibold"
      >
        Skip to program generator
      </a>
      <Navbar />
      <main>
        <Hero />
        <SocialProof />
        <HowItWorks />
        <ProductFeatures />
        <ProductShowcase />
        <SampleProgram />
        <FinalCTA />
        <ProgramGenerator />
      </main>
      <Footer />
      <CookieBanner />
    </div>
  );
}

export default App;
