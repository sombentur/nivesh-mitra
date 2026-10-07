"use client";

import { useSyncExternalStore } from "react";

/** True while the CSS media query matches (assumed true until the page is running in the browser). */
export function useMediaQuery(query: string) {
  return useSyncExternalStore(
    (onChange) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", onChange);
      return () => m.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => true,
  );
}

/** The sidebar (with the trading calendar) shows from this width up; below it the dashboard shows the calendar instead. */
export const SIDEBAR_QUERY = "(min-width: 1024px)";
