"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui";

type Options = {
  title: string;
  body?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** "danger" for things that remove or reset something */
  tone?: "default" | "danger";
};

let ask: ((o: Options) => Promise<boolean>) | null = null;

/**
 * "Are you sure?" in the app's own style. Use it like the browser's confirm(), but awaited:
 * `if (!(await confirmDialog({ title: "Remove this goal?" }))) return;`
 */
export function confirmDialog(o: Options): Promise<boolean> {
  return ask ? ask(o) : Promise.resolve(window.confirm(o.title));
}

/** Mounted once in the root layout. Uses the browser's own <dialog>, so focus stays inside it and Esc closes it. */
export function ConfirmHost() {
  const ref = useRef<HTMLDialogElement>(null);
  const resolver = useRef<((v: boolean) => void) | null>(null);
  const [opts, setOpts] = useState<Options | null>(null);

  useEffect(() => {
    ask = (o) =>
      new Promise<boolean>((resolve) => {
        resolver.current?.(false);
        resolver.current = resolve;
        setOpts(o);
      });
    return () => {
      ask = null;
    };
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!opts || !el || el.open) return;
    el.showModal();
    // Enter should never remove something by accident: a risky question starts on "Cancel"
    el.querySelector<HTMLButtonElement>(opts.tone === "danger" ? "[data-cancel]" : "[data-confirm]")?.focus();
  }, [opts]);

  function finish(answer: boolean) {
    resolver.current?.(answer);
    resolver.current = null;
    ref.current?.close();
    setOpts(null);
  }

  const danger = opts?.tone === "danger";
  return (
    <dialog
      ref={ref}
      className="nm-dialog"
      aria-labelledby="nm-confirm-title"
      onCancel={(e) => {
        e.preventDefault();
        finish(false);
      }}
      onClick={(e) => {
        if (e.target === ref.current) finish(false); // a click on the dimmed area outside the box
      }}
    >
      {opts && (
        <div className="p-6">
          <div className="flex items-start gap-4">
            <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${danger ? "bg-bad-soft text-bad" : "bg-brand-soft text-brand-strong"}`}>
              <svg viewBox="0 0 24 24" width={20} height={20} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                {danger ? <path d="M12 8.5v4.5m0 3v.5M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z" /> : <path d="M12 16v.5M9.5 9.2a2.6 2.6 0 1 1 3.9 2.3c-.8.5-1.4 1-1.4 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />}
              </svg>
            </span>
            <div className="min-w-0 flex-1">
              <h2 id="nm-confirm-title" className="text-lg font-semibold leading-snug">
                {opts.title}
              </h2>
              {opts.body && <div className="mt-1.5 text-sm leading-relaxed text-muted">{opts.body}</div>}
            </div>
          </div>
          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="secondary" onClick={() => finish(false)} data-cancel>
              {opts.cancelLabel ?? "Cancel"}
            </Button>
            <Button variant={danger ? "danger-solid" : "primary"} onClick={() => finish(true)} data-confirm>
              {opts.confirmLabel ?? "Confirm"}
            </Button>
          </div>
        </div>
      )}
    </dialog>
  );
}
