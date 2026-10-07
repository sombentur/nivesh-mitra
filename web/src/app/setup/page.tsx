"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api, type SetupStatus } from "@/lib/api";
import { Footer } from "@/components/AppShell";
import { Logo } from "@/components/Logo";
import { Button, Card, Field, inputClass, Notice, PageHeader, Spinner } from "@/components/ui";

const CODE = "mx-1 rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[13px] ring-1 ring-inset ring-border";

const STEPS = [
  <>
    Open{" "}
    <a className="font-medium text-brand-strong underline underline-offset-2" href="https://console.cloud.google.com/" target="_blank" rel="noreferrer">
      console.cloud.google.com
    </a>{" "}
    and sign in with the Google account you use for Groww.
  </>,
  <>
    At the top, click the project picker → <b>New project</b>. Name it <b>NiveshMitra</b> → <b>Create</b>, then make sure it
    is selected.
  </>,
  <>
    In the search bar type <b>Google Auth Platform</b> (older screens call it <b>OAuth consent screen</b>) → <b>Get started</b>.
    App name: <b>NiveshMitra</b>. Support email: your email. Audience: <b>External</b>. Contact email: your email. Agree and{" "}
    <b>Create</b>.
  </>,
  <>
    Go to <b>Audience</b> → <b>Test users</b> → <b>Add users</b> → add your own Gmail address. (While the app is in
    &quot;Testing&quot;, only the people listed here can ever sign in, which is exactly what we want.)
  </>,
  <>
    Go to <b>Clients</b> (or <b>Credentials</b>) → <b>Create client</b> → type <b>Web application</b>, name{" "}
    <b>NiveshMitra local</b>. Under <b>Authorized JavaScript origins</b> add both:
    <code className={CODE}>http://localhost</code>and
    <code className={CODE}>http://localhost:3000</code>. Leave redirect URIs empty → <b>Create</b>.
  </>,
  <>
    Copy the <b>Client ID</b> (it ends with <code className={CODE}>.apps.googleusercontent.com</code>) and paste it below. You
    don&apos;t need the client secret. The Client ID isn&apos;t a password; it only tells Google which app is asking.
  </>,
];

export default function SetupPage() {
  const router = useRouter();
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [clientId, setClientId] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<SetupStatus>("/setup/status").then(setStatus, (e) => setError(e.message));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post("/setup", { google_client_id: clientId, allowed_email: email });
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
      setSaving(false);
    }
  }

  return (
    <>
      <main className="nm-enter mx-auto w-full max-w-3xl flex-1 px-4 py-8 sm:px-6 sm:py-12">
        <Logo height={40} />
        <div className="mt-8">
          <PageHeader
            eyebrow="First-time setup"
            title="Create your sign-in key"
            description={
              <>
                Nivesh Mitra uses <b>Sign in with Google</b> plus a code from an authenticator app on your phone. Google needs a
                one-time &quot;login key&quot; (a Client ID) for your own copy of the app. It&apos;s free and takes about 5 minutes.
              </>
            }
          />
        </div>

        {status?.locked ? (
          <div className="mt-6">
            <Notice tone="good">
              Setup is already complete.{" "}
              <a className="font-medium underline underline-offset-2" href="/login">
                Go to sign in
              </a>
              .
            </Notice>
          </div>
        ) : (
          <div className="mt-8 grid gap-6">
            <Card title="1 · Create your Google login key">
              <ol className="grid gap-4 text-sm leading-relaxed">
                {STEPS.map((s, i) => (
                  <li key={i} className="flex gap-3.5">
                    <span className="num mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-navy text-[11px] font-semibold text-white">{i + 1}</span>
                    <span className="min-w-0 flex-1">{s}</span>
                  </li>
                ))}
              </ol>
              <p className="mt-5 border-t border-border pt-4 text-xs leading-relaxed text-muted">
                If a screen looks different, Google has renamed a menu. Look for &quot;OAuth&quot;, &quot;Clients&quot; or
                &quot;Credentials&quot;.
              </p>
            </Card>

            <Card title="2 · Connect it">
              <form onSubmit={submit} className="grid gap-5">
                <Field label="Google Client ID" hint="Ends with .apps.googleusercontent.com">
                  <input
                    className={inputClass}
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder="123456789012-abc….apps.googleusercontent.com"
                    required
                  />
                </Field>
                <Field label="Your Google email" hint="Only this account will be allowed to sign in.">
                  <input
                    className={inputClass}
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@gmail.com"
                    required
                  />
                </Field>
                {error && <Notice tone="bad">{error}</Notice>}
                <div>
                  <Button type="submit" disabled={saving}>
                    {saving && <Spinner />}
                    {saving ? "Saving…" : "Save and continue"}
                  </Button>
                </div>
              </form>
            </Card>
          </div>
        )}
      </main>
      <Footer />
    </>
  );
}
