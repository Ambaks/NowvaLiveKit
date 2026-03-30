import { Navbar } from '@/components/sections/Navbar';
import { Hero } from '@/components/sections/Hero';
import { ProductFeatures } from '@/components/sections/ProductFeatures';
import { ProductShowcase } from '@/components/sections/ProductShowcase';
import { SampleProgram } from '@/components/sections/SampleProgram';
import { ProgramGenerator } from '@/components/sections/ProgramGenerator';
import { Footer } from '@/components/sections/Footer';

function App() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <Hero />
      <ProductFeatures />
      <ProductShowcase />
      <SampleProgram />
      <ProgramGenerator />
      <Footer />
    </div>
  );
}

export default App;
