import Image from "next/image";

/* Server-rendered CSS-only intro: the page exists underneath from the first
   byte; globals.css runs the timeline and layout.tsx's inline script skips
   it after the first showing in a tab session. */
export function IntroLoader() {
  return (
    <div className="intro-loader" aria-hidden="true">
      <Image
        src="/logo-white.png"
        alt=""
        width={76}
        height={76}
        preload
        className="intro-loader__logo"
      />
      <div className="intro-loader__word">NOWVA</div>
      <div className="intro-loader__bar" />
      <div className="intro-loader__status">
        <span>Calibrating cameras</span>
        <span>Loading pose engine</span>
        <span>Coach online</span>
      </div>
    </div>
  );
}
