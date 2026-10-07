import type { Metadata, Viewport } from "next";
import { Geist_Mono, Inter, Outfit } from "next/font/google";
import { ConfirmHost } from "@/components/ConfirmDialog";
import "./globals.css";

// Inter for text and numbers (latin-ext carries the ₹ sign); Outfit for headings, close to the logo's lettering.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "latin-ext"],
  display: "swap",
});

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const THEME_BOOT = `try{var t=localStorage.getItem("nm-theme");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme="light"}`;

const LIGHT = "(prefers-color-scheme: light)";
const DARK = "(prefers-color-scheme: dark)";

export const metadata: Metadata = {
  title: "Nivesh Mitra",
  description: "Your personal, decision-only investment assistant",
  applicationName: "Nivesh Mitra",
  // The tab icon is the logo's mark on a transparent background. Browsers with a dark tab strip get the version whose
  // navy "N" is white, so it stays visible. /favicon.ico (in public/) covers anything that ignores these links.
  icons: {
    icon: [
      { url: "/brand/icon-light-32.png", sizes: "32x32", type: "image/png", media: LIGHT },
      { url: "/brand/icon-light-192.png", sizes: "192x192", type: "image/png", media: LIGHT },
      { url: "/brand/icon-dark-32.png", sizes: "32x32", type: "image/png", media: DARK },
      { url: "/brand/icon-dark-192.png", sizes: "192x192", type: "image/png", media: DARK },
    ],
    apple: [{ url: "/brand/apple-icon.png", sizes: "180x180", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: LIGHT, color: "#ffffff" },
    { media: DARK, color: "#0a1830" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${outfit.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        {/* Pick light/dark before the first paint: the saved choice, else the computer's setting. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body className="flex min-h-full flex-col">
        {children}
        <ConfirmHost />
      </body>
    </html>
  );
}
