"use client";

import { useEffect, useState } from "react";
import { confirmDialog } from "@/components/ConfirmDialog";
import { MoneyInput, NumberInput } from "@/components/inputs";
import { Badge, Button, inputClass, Notice } from "@/components/ui";
import { api, type Goal, type GoalInput, type ProfileRules } from "@/lib/api";
import { inr } from "@/lib/format";

const THIS_YEAR = new Date().getFullYear();
const EMPTY = { name: "", goal_type: "wealth", target_amount_today: null as number | null, target_year: THIS_YEAR + 10 as number | null };

export function GoalsEditor({ rules }: { rules: ProfileRules }) {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [draft, setDraft] = useState(EMPTY);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.get<Goal[]>("/goals").then(setGoals, (e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  const typeLabel = (v: string) => rules.questions.goal_types.find((t) => t.value === v)?.label ?? v;

  async function add() {
    if (!draft.target_amount_today || !draft.target_year) return;
    setError(null);
    try {
      const body: GoalInput = {
        name: draft.name.trim() || typeLabel(draft.goal_type),
        goal_type: draft.goal_type,
        target_amount_today: draft.target_amount_today,
        target_year: draft.target_year,
      };
      await api.post("/goals", body);
      setDraft(EMPTY);
      setAdding(false);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the goal");
    }
  }

  async function remove(g: Goal) {
    if (!(await confirmDialog({ title: `Remove the goal "${g.name}"?`, body: "You can add it again later.", confirmLabel: "Remove goal", tone: "danger" }))) return;
    await api.del(`/goals/${g.id}`);
    load();
  }

  return (
    <div className="grid gap-4">
      {goals.length === 0 && !adding && <p className="rounded-xl border border-dashed border-border-strong px-4 py-5 text-center text-sm text-muted">No goals yet. Add your first one below.</p>}
      {goals.map((g) => (
        <div key={g.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-surface p-3.5 text-sm shadow-xs">
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{g.name}</div>
            <div className="mt-0.5 text-xs text-muted">
              {typeLabel(g.goal_type)} · {g.target_year} ({g.years_away} {g.years_away === 1 ? "year" : "years"} away)
            </div>
          </div>
          <div className="text-right">
            <div className="num font-semibold">{inr(g.target_amount_today)}</div>
            <div className="num mt-0.5 text-xs text-muted">
              ≈ {inr(g.target_amount_future)} in {g.target_year} at {(g.inflation_rate * 100).toFixed(0)}% inflation
            </div>
          </div>
          {g.years_away < 3 && <Badge tone="warn">Under 3 years: mostly safe funds</Badge>}
          <button onClick={() => remove(g)} className="rounded-lg px-2 py-1 text-xs font-medium text-muted hover:bg-bad-soft hover:text-bad">
            Remove
          </button>
        </div>
      ))}

      {adding ? (
        <div className="nm-enter grid gap-4 rounded-2xl border border-border bg-surface-2 p-4 sm:p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium">Type of goal</span>
              <select
                className={`${inputClass} mt-1.5`}
                value={draft.goal_type}
                onChange={(e) => setDraft({ ...draft, goal_type: e.target.value })}
              >
                {rules.questions.goal_types.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-medium">Name (optional)</span>
              <input
                className={`${inputClass} mt-1.5`}
                value={draft.name}
                placeholder={typeLabel(draft.goal_type)}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </label>
            <MoneyInput
              label="How much, in today's money?"
              hint="What it would cost if you bought it today. We add inflation for you."
              value={draft.target_amount_today}
              onChange={(v) => setDraft({ ...draft, target_amount_today: v })}
            />
            <NumberInput
              label="Target year"
              value={draft.target_year}
              onChange={(v) => setDraft({ ...draft, target_year: v })}
              min={THIS_YEAR}
              max={THIS_YEAR + 60}
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={add} disabled={!draft.target_amount_today || !draft.target_year}>
              Save goal
            </Button>
            <Button variant="secondary" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button variant="secondary" onClick={() => setAdding(true)}>
            + Add a goal
          </Button>
        </div>
      )}
      {error && <Notice tone="bad">{error}</Notice>}
    </div>
  );
}
