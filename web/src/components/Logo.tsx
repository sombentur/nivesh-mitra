import Image from "next/image";

// The files in public/brand are cut straight from the logo artwork: same proportions, transparent background.
const FULL = { light: "/brand/logo.png", reverse: "/brand/logo-reverse.png", width: 720, height: 127 };
const MARK = { light: "/brand/mark.png", reverse: "/brand/mark-reverse.png", width: 330, height: 256 };

type Tone = "auto" | "reverse";

function Art({ art, height, tone, alt, className }: { art: typeof FULL; height: number; tone: Tone; alt: string; className: string }) {
  const width = Math.round((height * art.width) / art.height);
  const shared = { width, height, style: { height, width: "auto" }, unoptimized: true, draggable: false } as const;
  if (tone === "reverse") return <Image {...shared} src={art.reverse} alt={alt} loading="eager" className={`block shrink-0 ${className}`} />;
  // Light theme: the logo exactly as supplied. Dark theme: the same artwork with its navy parts in white.
  return (
    <>
      <Image {...shared} src={art.light} alt={alt} className={`block shrink-0 dark:hidden ${className}`} />
      <Image {...shared} src={art.reverse} alt={alt} className={`hidden shrink-0 dark:block ${className}`} />
    </>
  );
}

/** The full Nivesh Mitra logo (mark + name). `tone="reverse"` is for navy panels in either theme. */
export function Logo({ height = 30, tone = "auto", className = "" }: { height?: number; tone?: Tone; className?: string }) {
  return <Art art={FULL} height={height} tone={tone} alt="Nivesh Mitra" className={className} />;
}

/** Just the "N" mark, for tight spots and loading screens. */
export function LogoMark({ height = 32, tone = "auto", className = "", alt = "Nivesh Mitra" }: { height?: number; tone?: Tone; className?: string; alt?: string }) {
  return <Art art={MARK} height={height} tone={tone} alt={alt} className={className} />;
}
