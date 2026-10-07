"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, type Me, type OnboardingStatus, type SetupStatus } from "@/lib/api";
import { DISCLAIMER, Notice } from "@/components/ui";
import { SIDEBAR_QUERY, useMediaQuery } from "@/lib/useMediaQuery";
import { IconHome, IconLayers, IconLogout, IconSettings, IconShield, IconTarget, IconTrend, IconUser } from "@/components/icons";
import { Logo } from "@/components/Logo";
import { MarketTicker } from "@/components/MarketTicker";
import { RefreshButton } from "@/components/RefreshButton";
import { ThemeToggle } from "@/components/ThemeToggle";
import { TradingCalendar } from "@/components/TradingCalendar";

const NAV = [
  { href: "/", label: "Dashboard", icon: IconHome },
  { href: "/plan", label: "My plan", icon: IconTarget },
  { href: "/funds", label: "Mutual funds", icon: IconLayers },
  { href: "/trading", label: "Trading", icon: IconTrend },
  { href: "/profile", label: "My profile", icon: IconUser },
  { href: "/settings", label: "Settings", icon: IconSettings },
];

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

export function Footer() {
  return (
    <footer className="mx-auto w-full max-w-[1680px] px-4 pb-8 pt-2 sm:px-8">
      <p className="border-t border-border pt-5 text-xs leading-relaxed text-muted">
        {DISCLAIMER} Nivesh Mitra is a personal decision-support tool, not a SEBI-registered adviser. It never places orders.
      </p>
    </footer>
  );
}

/** Full-screen "one moment" state, shown while the app works out who you are. */
export function Splash({ label }: { label: string }) {
  return (
    <main className="grid min-h-screen flex-1 place-items-center px-6">
      <div role="status" className="flex w-60 flex-col items-center gap-5 text-sm text-muted">
        <Logo height={34} />
        <div className="nm-progress w-full" />
        <span>{label}</span>
      </div>
    </main>
  );
}

/** Wraps signed-in pages: sends you to setup, login or onboarding when needed. */
export function AppShell({ children, allowIncompleteOnboarding = false }: { children: ReactNode; allowIncompleteOnboarding?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0); // bumped by the Refresh button
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const hasSidebar = useMediaQuery(SIDEBAR_QUERY);

  useEffect(() => {
    (async () => {
      try {
        const setup = await api.get<SetupStatus>("/setup/status");
        if (!setup.configured) return router.replace("/setup");
        const who = await api.get<Me>("/auth/me");
        if (!allowIncompleteOnboarding) {
          const onboarding = await api.get<OnboardingStatus>("/onboarding/status");
          if (!onboarding.complete) return router.replace("/onboarding");
        }
        setMe(who);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) router.replace("/login");
        else setError(e instanceof Error ? e.message : "Something went wrong");
      }
    })();
  }, [router, allowIncompleteOnboarding]);

  async function logout() {
    await api.post("/auth/logout");
    router.replace("/login");
  }

  if (error)
    return (
      <main className="mx-auto grid w-full max-w-xl flex-1 content-center gap-6 p-6">
        <Logo height={30} />
        <Notice tone="bad">{error}</Notice>
      </main>
    );
  if (!me) return <Splash label="Opening your dashboard…" />;

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <MeContext.Provider value={me}>
      <div className="min-h-screen lg:flex">
        {/* Desktop: fixed sidebar */}
        <aside className="sticky top-0 hidden h-screen w-[17rem] shrink-0 flex-col border-r border-border bg-surface shadow-[1px_0_24px_-12px_rgb(0_30_74/0.18)] lg:flex">
          <Link href="/" className="rounded-lg px-5 pb-1 pt-6" aria-label="Nivesh Mitra: dashboard">
            <Logo height={31} />
          </Link>
          <p className="px-5 pb-5 text-[11px] font-medium tracking-wide text-muted">Your investment co-pilot</p>
          {/* everything between the logo and the account row scrolls if the window is short */}
          <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto pb-3">
            <nav className="grid gap-1 px-3 text-sm" aria-label="Main">
              {NAV.map(({ href, label, icon: Icon }) => {
                const active = isActive(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 font-medium ${
                      active ? "bg-navy text-white shadow-[0_8px_18px_-10px_var(--navy)]" : "text-muted hover:bg-surface-2 hover:text-text"
                    }`}
                  >
                    <Icon className={active ? "text-ink-accent" : "text-subtle group-hover:text-brand"} />
                    {label}
                    {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-ink-accent" />}
                  </Link>
                );
              })}
            </nav>
            <div className="mx-3 mt-4 rounded-xl border border-brand/20 bg-brand-soft/70 p-3 text-xs">
              <p className="flex items-center gap-2 font-semibold text-text">
                <IconShield className="text-brand" width={16} height={16} /> Decision-only
              </p>
              <p className="mt-1.5 leading-relaxed text-muted">Never places orders. You buy on Groww yourself.</p>
            </div>
            {hasSidebar && <TradingCalendar key={version} className="mx-3 mt-3 rounded-xl border border-border bg-surface-2/70 p-3" />}
          </div>
          <div className="px-3 pb-2 pt-1">
            <ThemeToggle />
          </div>
          <div className="border-t border-border px-4 py-4">
            <div className="flex items-center gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-navy text-xs font-semibold uppercase text-white ring-2 ring-brand/40">
                {(me.name || me.email).slice(0, 1)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{me.name || "Signed in"}</span>
                <span className="block truncate text-[11px] text-muted">{me.email}</span>
              </span>
              <button onClick={logout} title="Sign out" aria-label="Sign out" className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-text">
                <IconLogout />
              </button>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* Mobile and tablet: frosted top bar with scrollable tabs */}
          <header className="glass sticky top-0 z-30 border-b border-border lg:hidden">
            <div className="flex items-center justify-between gap-3 px-4 py-3">
              <Link href="/" className="rounded-lg" aria-label="Nivesh Mitra: dashboard">
                <Logo height={26} />
              </Link>
              <div className="flex items-center gap-1">
                <ThemeToggle compact />
                <button onClick={logout} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium text-muted hover:bg-surface-2 hover:text-text">
                  <IconLogout width={16} height={16} /> Sign out
                </button>
              </div>
            </div>
            <nav className="no-scrollbar flex gap-1.5 overflow-x-auto px-3 pb-2.5 text-sm" aria-label="Main">
              {NAV.map(({ href, label, icon: Icon }) => {
                const active = isActive(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 font-medium ${
                      active ? "bg-navy text-white shadow-xs" : "text-muted hover:bg-surface-2 hover:text-text"
                    }`}
                  >
                    <Icon width={15} height={15} className={active ? "text-ink-accent" : ""} />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </header>
          <div className="flex items-stretch lg:sticky lg:top-0 lg:z-30">
            <div className="min-w-0 flex-1">
              <MarketTicker key={version} />
            </div>
            <RefreshButton onReload={reload} />
          </div>
          {/* the key makes Refresh rebuild the page content, so every section reads its data again */}
          <main key={version} className="nm-enter mx-auto w-full max-w-[1680px] flex-1 px-4 py-6 sm:px-8 sm:py-8">
            {children}
          </main>
          <Footer />
        </div>
      </div>
    </MeContext.Provider>
  );
}
