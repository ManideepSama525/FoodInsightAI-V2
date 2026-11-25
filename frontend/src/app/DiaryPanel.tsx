"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, BookOpen, CalendarDays, Check, Clock3, LoaderCircle, Plus, RefreshCw, Trash2, Utensils } from "lucide-react";
import { api, type DiaryEntry, type Food, type Nutrient } from "@/lib/api";

type MealType = DiaryEntry["meal_type"];

const meals: { id: MealType; label: string; time: string }[] = [
  { id: "breakfast", label: "Breakfast", time: "Morning" },
  { id: "lunch", label: "Lunch", time: "Midday" },
  { id: "dinner", label: "Dinner", time: "Evening" },
  { id: "snack", label: "Snacks", time: "Anytime" },
];

function localDateKey(value: string | Date) {
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function todayKey() {
  return localDateKey(new Date());
}

function formatNumber(value: unknown, unit: string) {
  const numericValue =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : NaN;

  return Number.isFinite(numericValue)
    ? `${numericValue.toFixed(2)} ${unit}`
    : "Not reported";
}

export default function DiaryPanel() {
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [foods, setFoods] = useState<Food[]>([]);
  const [foodId, setFoodId] = useState("");
  const [grams, setGrams] = useState(100);
  const [meal, setMeal] = useState<MealType>("breakfast");
  const [nutrients, setNutrients] = useState<Nutrient[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const todayEntries = useMemo(
    () => entries.filter(entry => localDateKey(entry.consumed_at) === todayKey()),
    [entries]
  );

  const grouped = useMemo(
    () => meals.map(item => ({
      ...item,
      entries: todayEntries.filter(entry => entry.meal_type === item.id),
    })),
    [todayEntries]
  );

  const loadDiary = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [diary, catalog] = await Promise.all([api.diary(), api.localFoods()]);
      setEntries(diary);
      setFoods(catalog);
      if (!foodId && catalog.length > 0) setFoodId(String(catalog[0].id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load your food diary.");
    } finally {
      setLoading(false);
    }
  }, [foodId]);

  useEffect(() => {
    void loadDiary();
  }, [loadDiary]);

  useEffect(() => {
    let active = true;

    async function calculateTotals() {
      if (todayEntries.length === 0) {
        setNutrients([]);
        return;
      }

      const results = await Promise.allSettled(
        todayEntries.map(entry => api.calculateFood(entry.food_id, entry.quantity_g))
      );

      if (!active) return;

      const totals = new Map<string, Nutrient>();

      for (const result of results) {
        if (result.status !== "fulfilled") continue;
        for (const nutrient of result.value.nutrients) {
          const key = nutrient.nutrient_key;
          const existing = totals.get(key);
          if (!existing) {
            totals.set(key, { ...nutrient });
          } else if (existing.amount !== null && nutrient.amount !== null) {
            existing.amount += nutrient.amount;
          } else {
            existing.amount = null;
          }
        }
      }

      setNutrients(Array.from(totals.values()));
    }

    void calculateTotals();
    return () => { active = false; };
  }, [todayEntries]);

  async function addEntry(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!foodId || grams <= 0) return;

    setSaving(true);
    setError("");
    setMessage("");

    try {
      await api.addDiaryEntry({
        food_id: Number(foodId),
        quantity_g: grams,
        meal_type: meal,
      });
      setMessage("Food added to today's diary.");
      await loadDiary();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add this food.");
    } finally {
      setSaving(false);
    }
  }

  async function removeEntry(id: number) {
    setError("");
    try {
      await api.deleteDiaryEntry(id);
      setEntries(current => current.filter(entry => entry.id !== id));
      setMessage("Diary entry removed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove this entry.");
    }
  }

  const selectedFood = foods.find(food => food.id === Number(foodId));
  const dateLabel = new Date().toLocaleDateString(undefined, {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
  });

  return (
    <section className="diary-page">
      <div className="page-intro diary-intro">
        <p className="eyebrow">PERSONAL FOOD LOG</p>
        <h1>Your daily <em>diary.</em></h1>
        <p>Record what you eat and review nutrient totals calculated from your food records.</p>
      </div>

      <div className="diary-datebar">
        <div><CalendarDays size={18}/><span>{dateLabel}</span></div>
        <button type="button" className="text-button" onClick={() => void loadDiary()}>
          <RefreshCw size={15}/> Refresh
        </button>
      </div>

      {message && <div className="diary-message"><Check size={16}/>{message}</div>}
      {error && <div className="diary-error" role="alert">{error}</div>}

      <section className="diary-summary">
        <div className="diary-summary-heading">
          <div><p className="eyebrow">TODAY&apos;S INTAKE</p><h2>Nutrition summary</h2></div>
          <span className="diary-count">{todayEntries.length} {todayEntries.length === 1 ? "entry" : "entries"}</span>
        </div>
        {loading ? (
          <div className="diary-loading"><LoaderCircle className="spin"/> Loading your diary...</div>
        ) : nutrients.length === 0 ? (
          <div className="diary-empty-summary"><Activity size={22}/><span>Log a food to see its calculated nutrient values here.</span></div>
        ) : (
          <div className="diary-nutrient-grid">
            {nutrients.map(item => (
              <div className="diary-nutrient" key={item.nutrient_key}>
                <span>{item.display_name}</span>
                <strong>{formatNumber(item.amount, item.unit)}</strong>
                <small>Based on today&apos;s logged portions</small>
              </div>
            ))}
          </div>
        )}
        <p className="diary-disclaimer">Totals include nutrients reported by the underlying food records. Unreported values are not estimated.</p>
      </section>

      <div className="diary-columns">
        <section className="diary-add-panel">
          <div className="diary-panel-heading"><span className="diary-panel-icon"><Plus size={19}/></span><div><p className="eyebrow">NEW ENTRY</p><h2>Add food</h2></div></div>
          <form onSubmit={addEntry} className="diary-form">
            <label>Food from your catalog
              <select value={foodId} onChange={event => setFoodId(event.target.value)} required>
                <option value="">Choose a food</option>
                {foods.map(food => <option key={food.id} value={food.id}>{food.name}</option>)}
              </select>
            </label>
            {selectedFood && <p className="diary-food-source">Source: {selectedFood.source}</p>}
            <label>Meal
              <select value={meal} onChange={event => setMeal(event.target.value as MealType)}>
                {meals.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
            <label>Portion size (grams)
              <input type="number" min="1" max="100000" step="1" value={grams} onChange={event => setGrams(Number(event.target.value))} required/>
            </label>
            <button className="button button-primary full-button" disabled={saving || loading || !foodId || grams <= 0}>
              {saving ? <LoaderCircle className="spin" size={16}/> : <Plus size={16}/>}
              Add to diary
            </button>
            {foods.length === 0 && !loading && <p className="diary-hint"><BookOpen size={15}/> No catalog foods found. Import foods in Nutrition Explorer first.</p>}
          </form>
        </section>

        <section className="diary-meals-panel">
          <div className="diary-panel-heading"><span className="diary-panel-icon"><Utensils size={19}/></span><div><p className="eyebrow">MEAL HISTORY</p><h2>Today&apos;s meals</h2></div></div>
          {loading ? <div className="diary-loading"><LoaderCircle className="spin"/> Loading entries...</div> :
            grouped.map(group => (
              <section className="diary-meal-group" key={group.id}>
                <div className="diary-meal-heading"><div><h3>{group.label}</h3><span>{group.time}</span></div><span>{group.entries.length}</span></div>
                {group.entries.length === 0 ? (
                  <p className="diary-meal-empty">No foods logged yet.</p>
                ) : group.entries.map(entry => (
                  <article className="diary-entry" key={entry.id}>
                    <div className="diary-entry-icon"><Utensils size={16}/></div>
                    <div className="diary-entry-info"><strong>{entry.food_name}</strong><span>{entry.quantity_g} g · {new Date(entry.consumed_at).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})}</span></div>
                    <button type="button" className="diary-delete" onClick={() => void removeEntry(entry.id)} aria-label={`Remove ${entry.food_name}`} title="Remove entry"><Trash2 size={16}/></button>
                  </article>
                ))}
              </section>
            ))
          }
          {!loading && todayEntries.length === 0 && <p className="diary-first-entry"><Clock3 size={16}/> Your meals will appear here as you log them.</p>}
        </section>
      </div>
    </section>
  );
}