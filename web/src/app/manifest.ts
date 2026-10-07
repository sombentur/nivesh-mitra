import type { MetadataRoute } from "next";

/** Lets the browser install Nivesh Mitra as an app (its own window and icon) on this PC. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Nivesh Mitra",
    short_name: "Nivesh Mitra",
    description: "Your personal, decision-only investment assistant",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#001e4a",
    icons: [
      { src: "/brand/icon-light-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/brand/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/brand/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
