"use client";

import Script from "next/script";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, type SetupStatus } from "@/lib/api";
import { Footer } from "@/components/AppShell";
import { IconPulse, IconShield, IconTarget } from "@/components/icons";
import { Logo } from "@/components/Logo";
import { Button, Field, inputClass, Notice, Skeleton, Spinner } from "@/components/ui";

type GoogleId = {
  initialize: (opts: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: string }) => void;
  renderButton: (el: HTMLElement, opts: Record<string, string | number>) => void;
};
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

type Stage = "google" | "totp_setup" | "totp";

const POINTS: { icon: ReactNode; title: string; text: string }[] = [
  { icon: <IconShield width={18} height={18} />, title: "Decision-only", text: "It never places orders. You buy on Groww yourself." },
  { icon: <IconTarget width={18} height={18} />, title: "Honest by design", text: "Ranges, confidence and risks on every idea. “Do nothing today” is a valid answer." },
  { icon: <IconPulse width={18} height={18} />, title: "Private", text: "Runs on this PC. Keys are encrypted, and your passwords are never asked for." },
];

/** Navy side panel on wide screens: what the app is, in three lines. */
function Welcome() {
  return (
    <section className="ink-panel on-ink relative hidden overflow-hidden p-12 lg:flex lg:flex-col lg:justify-center xl:p-16">
      {/* a rising line, echoing the arrow in the logo */}
      <svg viewBox="0 0 600 300" preserveAspectRatio="none" className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 w-full opacity-60" aria-hidden="true">
        <defs>
          <linearGradient id="nm-welcome-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--ink-accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--ink-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M0,250 L60,232 L120,240 L180,205 L240,214 L300,170 L360,182 L420,128 L480,140 L540,84 L600,52 L600,300 L0,300 Z" fill="url(#nm-welcome-fill)" />
        <path d="M0,250 L60,232 L120,240 L180,205 L240,214 L300,170 L360,182 L420,128 L480,140 L540,84 L600,52" fill="none" stroke="var(--ink-accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="relative max-w-lg">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-ink-accent">Your investment co-pilot</p>
        <h2 className="mt-4 text-4xl font-semibold leading-[1.12] text-white xl:text-5xl">
          Clear decisions.
          <br />
          Your money, your call.
        </h2>
        <p className="mt-5 text-[15px] leading-relaxed text-ink-muted">
          Nivesh Mitra studies Indian mutual funds and stocks and tells you, in plain words, what it would do and why.
        </p>
        <ul className="mt-9 grid gap-3">
          {POINTS.map((p) => (
            <li key={p.title} className="glass-ink flex items-start gap-3.5 rounded-2xl p-4">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/10 text-ink-accent">{p.icon}</span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-white">{p.title}</span>
                <span className="mt-0.5 block text-[13px] leading-relaxed text-ink-muted">{p.text}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Steps({ stage }: { stage: Stage }) {
  const second = stage !== "google";
  const steps = [
    { n: 1, label: "Google account", done: second, current: !second },
    { n: 2, label: "Authenticator code", done: false, current: second },
  ];
  return (
    <ol className="flex items-center gap-3 text-xs font-medium">
      {steps.map((s, i) => (
        <li key={s.n} className="flex items-center gap-2" aria-current={s.current ? "step" : undefined}>
          {i > 0 && <span className={`h-px w-6 ${second ? "bg-brand" : "bg-border-strong"}`} />}
          <span className={`num grid h-6 w-6 place-items-center rounded-full text-[11px] font-semibold ${s.done ? "bg-brand text-on-brand" : s.current ? "bg-navy text-white" : "bg-surface-3 text-muted"}`}>
            {s.done ? "✓" : s.n}
          </span>
          <span className={s.current ? "text-text" : "text-muted"}>{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [gsiLoaded, setGsiLoaded] = useState(false);
  const [stage, setStage] = useState<Stage>("google");
  const [qr, setQr] = useState<{ qr_svg: string; manual_key: string } | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<SetupStatus>("/setup/status").then(
      (s) => (s.configured ? setClientId(s.google_client_id) : router.replace("/setup")),
      (e) => setError(e.message),
    );
  }, [router]);

  const onGoogle = useCallback(async ({ credential }: { credential: string }) => {
    setError(null);
    try {
      const { next } = await api.post<{ next: Stage }>("/auth/google", { credential });
      if (next === "totp_setup") setQr(await api.get("/auth/totp/setup"));
      setStage(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
    }
  }, []);

  useEffect(() => {
    if (!gsiLoaded || !clientId || stage !== "google" || !buttonRef.current || !window.google) return;
    window.google.accounts.id.initialize({ client_id: clientId, callback: onGoogle, ux_mode: "popup" });
    window.google.accounts.id.renderButton(buttonRef.current, {
      theme: "outline",
      size: "large",
      shape: "pill",
      text: "signin_with",
      width: 280,
    });
  }, [gsiLoaded, clientId, stage, onGoogle]);

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/totp", { code });
      router.replace("/");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Code not accepted";
      setError(msg);
      if (msg.includes("expired")) setStage("google");
      setBusy(false);
    }
  }

  return (
    <>
      <Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" onLoad={() => setGsiLoaded(true)} />
      <main className="grid min-h-screen flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Welcome />
        <section className="flex min-w-0 flex-col">
          <div className="flex flex-1 flex-col justify-center px-4 py-10 sm:px-8">
          <div className="nm-enter mx-auto w-full max-w-md">
            <Logo height={44} />
            <h1 className="mt-8 text-[28px] font-semibold leading-tight">Sign in</h1>
            <p className="mt-1.5 text-sm text-muted">Two quick steps keep your account yours alone.</p>

            <div className="glass mt-6 rounded-3xl border border-border p-6 sm:p-7">
              <Steps stage={stage} />

              <div className="mt-6">
                {stage === "google" && (
                  <div className="grid gap-4">
                    <p className="text-sm text-muted">Sign in with the Google account you chose during setup.</p>
                    <div ref={buttonRef} className="min-h-11" />
                    {!gsiLoaded && (
                      <div role="status">
                        <Skeleton className="h-11 w-[280px] max-w-full rounded-full" />
                        <span className="sr-only">Loading Google sign-in…</span>
                      </div>
                    )}
                  </div>
                )}

                {stage === "totp_setup" && qr && (
                  <div className="grid gap-4">
                    <p className="text-sm leading-relaxed">
                      <b>One-time step:</b> set up your authenticator app. Install <b>Google Authenticator</b> or{" "}
                      <b>Microsoft Authenticator</b> on your phone, tap <b>+</b>, and scan this code.
                    </p>
                    <div
                      className="mx-auto w-fit rounded-2xl border border-border bg-white p-2.5 shadow-xs"
                      dangerouslySetInnerHTML={{ __html: qr.qr_svg }}
                    />
                    <details className="text-xs text-muted">
                      <summary className="font-medium hover:text-text">Can&apos;t scan? Enter this key manually</summary>
                      <code className="mt-2 block break-all rounded-lg bg-surface-2 p-2.5 font-mono text-text">{qr.manual_key}</code>
                    </details>
                  </div>
                )}

                {(stage === "totp" || stage === "totp_setup") && (
                  <form onSubmit={submitCode} className={`grid gap-4 ${stage === "totp_setup" ? "mt-5" : ""}`}>
                    <Field label="6-digit code" hint="From the NiveshMitra entry in your authenticator app.">
                      <input
                        className={`${inputClass} py-3 text-center font-mono text-xl tracking-[0.45em]`}
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                        autoFocus
                        required
                      />
                    </Field>
                    <Button type="submit" disabled={busy || code.length !== 6}>
                      {busy && <Spinner />}
                      {busy ? "Checking…" : "Verify and open"}
                    </Button>
                  </form>
                )}

                {error && (
                  <div className="mt-4">
                    <Notice tone="bad">{error}</Notice>
                  </div>
                )}
              </div>
            </div>

            <p className="mt-5 flex items-start gap-2 text-xs leading-relaxed text-muted">
              <IconShield width={15} height={15} className="mt-0.5 shrink-0 text-brand" />
              Nivesh Mitra never asks for your Google or Groww password. Google checks your password on its own page.
            </p>
          </div>
          </div>
          <Footer />
        </section>
      </main>
    </>
  );
}
