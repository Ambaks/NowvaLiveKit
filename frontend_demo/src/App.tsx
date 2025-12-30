import { Hero } from '@/components/sections/Hero';
import { HowItWorks } from '@/components/sections/HowItWorks';
import { SampleProgram } from '@/components/sections/SampleProgram';
import { ValueProposition } from '@/components/sections/ValueProposition';
import { ProgramGenerator } from '@/components/sections/ProgramGenerator';
import { TheFuture } from '@/components/sections/TheFuture';
import { Footer } from '@/components/sections/Footer';

function App() {
  return (
    <div className="min-h-screen bg-background">
      <Hero />
      <HowItWorks />
      <SampleProgram />
      <ValueProposition />
      <ProgramGenerator />
      <TheFuture />
      <Footer />
    </div>
  );
}

export default App;
