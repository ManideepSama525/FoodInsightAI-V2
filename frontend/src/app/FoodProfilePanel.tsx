"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, LoaderCircle, Save, ShieldCheck, Utensils } from "lucide-react";
import { api, type FoodProfile, type FoodSafetyResult, type FoodRecommendationResponse, type Recipe } from "@/lib/api";


const preferences = [
  "vegetarian", "vegan", "eggetarian", "pescatarian",
  "non-vegetarian", "Jain", "halal", "kosher",
];

const goalOptions = [
  "high protein", "high fiber", "low calorie", "weight management",
  "muscle building", "balanced nutrition", "low sugar",
];

function lines(values: string[]) {
  return values.join("\n");
}

function parseLines(value: string) {
  return value.split(/[\n,]/).map(item => item.trim()).filter(Boolean);
}

function parseConcerns(value: string) {
  return value.split("\n").map(line => {
    const [rawName, rawSeverity] = line.split(":");
    const name = rawName?.trim();
    const severity = rawSeverity?.trim().toLowerCase() || "unspecified";
    if (!name) return null;
    return {
      name,
      severity: ["mild", "moderate", "severe", "unspecified"].includes(severity)
        ? severity as "mild" | "moderate" | "severe" | "unspecified"
        : "unspecified" as const,
    };
  }).filter((item): item is NonNullable<typeof item> => item !== null);
}

function concernLines(items: FoodProfile["allergies"]) {
  return items.map(item => `${item.name}:${item.severity}`).join("\n");
}

export default function FoodProfilePanel({ recipes }: { recipes: Recipe[] }) {
  const [, setProfile] = useState<FoodProfile>({
    allergies: [],
    intolerances: [],
    dietary_preferences: [],
    goals: [],
    disliked_foods: [],
    cuisine_interests: [],
  });
  const [allergies, setAllergies] = useState("");
  const [intolerances, setIntolerances] = useState("");
  const [dietary, setDietary] = useState<string[]>([]);
  const [goals, setGoals] = useState<string[]>([]);
  const [disliked, setDisliked] = useState("");
  const [cuisines, setCuisines] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [checks, setChecks] = useState<Record<number, FoodSafetyResult>>({});
  const [checkingRecipe, setCheckingRecipe] = useState<number | null>(null);
  const [recommendations, setRecommendations] = useState<FoodRecommendationResponse | null>(null);
  const [recommendationsLoading, setRecommendationsLoading] = useState(false);
  const [recommendationsError, setRecommendationsError] = useState("");

  const loadRecommendations = useCallback(async () => {
    setRecommendationsLoading(true);
    setRecommendationsError("");
    try {
      const result = await api.foodRecommendations();
      setRecommendations(result);
    } catch (e) {
      setRecommendationsError(
        e instanceof Error ? e.message : "Could not load food recommendations."
      );
    } finally {
      setRecommendationsLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    api.getFoodProfile().then(data => {
      if (!active) return;
      setProfile(data);
      setAllergies(concernLines(data.allergies));
      setIntolerances(concernLines(data.intolerances));
      setDietary(data.dietary_preferences);
      setGoals(data.goals);
      setDisliked(lines(data.disliked_foods));
      setCuisines(lines(data.cuisine_interests));
      void loadRecommendations();
    }).catch(e => {
      if (active) setError(e instanceof Error ? e.message : "Could not load profile.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [loadRecommendations]);

  function toggle(value: string, current: string[], setter: (items: string[]) => void) {
    setter(current.includes(value)
      ? current.filter(item => item !== value)
      : [...current, value]);
  }

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const payload: FoodProfile = {
        allergies: parseConcerns(allergies),
        intolerances: parseConcerns(intolerances),
        dietary_preferences: dietary,
        goals,
        disliked_foods: parseLines(disliked),
        cuisine_interests: parseLines(cuisines),
      };
      const saved = await api.updateFoodProfile(payload);
      setProfile(saved);
      setMessage("Your food profile has been saved.");
      await loadRecommendations();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save your profile.");
    } finally {
      setSaving(false);
    }
  }

  async function checkRecipe(recipeId: number) {
    setCheckingRecipe(recipeId);
    setError("");
    try {
      const result = await api.assessRecipe(recipeId);
      setChecks(current => ({ ...current, [recipeId]: result }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Recipe safety check failed.");
    } finally {
      setCheckingRecipe(null);
    }
  }

  if (loading) {
    return <div className="profile-loading"><LoaderCircle className="spin"/> Loading your food profile...</div>;
  }

  return (
    <section className="profile-page">
      <div className="page-intro">
        <p className="eyebrow">YOUR PERSONAL FOOD CONTEXT</p>
        <h1>Food <em>profile.</em></h1>
        <p>Record your dietary requirements and food preferences. These settings are private to your account and are used for personalized screening.</p>
      </div>

      {message && <div className="profile-message"><Check size={16}/>{message}</div>}
      {error && <div className="profile-error" role="alert">{error}</div>}

      <form className="profile-form" onSubmit={saveProfile}>
        <section className="profile-section">
          <div className="profile-heading">
            <span><ShieldCheck size={19}/></span>
            <div><h2>Allergies</h2><p>Record known food allergies and their reported severity.</p></div>
          </div>
          <label>One entry per line: ingredient:severity
            <textarea rows={4} value={allergies} onChange={e => setAllergies(e.target.value)} placeholder={"peanut:severe\nmilk:moderate\negg:unspecified"}/>
          </label>
          <small className="profile-hint">Severity values: mild, moderate, severe, unspecified. These are user-reported, not medically verified.</small>
        </section>

        <section className="profile-section">
          <div className="profile-heading">
            <span><AlertTriangle size={19}/></span>
            <div><h2>Intolerances</h2><p>Keep intolerances separate from allergies.</p></div>
          </div>
          <label>One entry per line: ingredient:severity
            <textarea rows={3} value={intolerances} onChange={e => setIntolerances(e.target.value)} placeholder={"lactose:moderate\ngluten:unspecified"}/>
          </label>
        </section>

        <section className="profile-section">
          <div className="profile-heading">
            <span><Utensils size={19}/></span>
            <div><h2>Dietary preferences</h2><p>Select the eating patterns you follow.</p></div>
          </div>
          <div className="profile-chip-grid">
            {preferences.map(item => (
              <label className={`profile-chip ${dietary.includes(item) ? "selected" : ""}`} key={item}>
                <input type="checkbox" checked={dietary.includes(item)} onChange={() => toggle(item, dietary, setDietary)}/>
                {item}
              </label>
            ))}
          </div>
        </section>

        <section className="profile-section">
          <div className="profile-heading">
            <span><Check size={19}/></span>
            <div><h2>Nutrition goals</h2><p>Choose goals to guide future recommendations.</p></div>
          </div>
          <div className="profile-chip-grid">
            {goalOptions.map(item => (
              <label className={`profile-chip ${goals.includes(item) ? "selected" : ""}`} key={item}>
                <input type="checkbox" checked={goals.includes(item)} onChange={() => toggle(item, goals, setGoals)}/>
                {item}
              </label>
            ))}
          </div>
        </section>

        <section className="profile-section">
          <h2>Foods you dislike or avoid</h2>
          <p>These are preferences, not allergy records. Enter one food per line.</p>
          <textarea rows={3} value={disliked} onChange={e => setDisliked(e.target.value)} placeholder={"mushroom\nolives"}/>
        </section>

        <section className="profile-section">
          <h2>Cuisine interests</h2>
          <p>Enter cuisines you are interested in exploring.</p>
          <textarea rows={3} value={cuisines} onChange={e => setCuisines(e.target.value)} placeholder={"Indian\nMediterranean\nEast Asian"}/>
        </section>

        <div className="profile-save-row">
          <p>Your profile is stored against your signed-in account.</p>
          <button className="button button-primary" disabled={saving}>
            {saving ? <LoaderCircle className="spin" size={16}/> : <Save size={16}/>}
            Save food profile
          </button>
        </div>
      </form>

      <section className="profile-recommendations">
        <div className="profile-heading">
          <span><Utensils size={19}/></span>
          <div>
            <h2>Food recommendations</h2>
            <p>Ranked against your saved nutrition goals using available local catalog data.</p>
          </div>
          <button
            type="button"
            className="button button-secondary recommendation-refresh"
            onClick={() => void loadRecommendations()}
            disabled={recommendationsLoading}
          >
            {recommendationsLoading
              ? <LoaderCircle className="spin" size={15}/>
              : <Check size={15}/>}
            Refresh
          </button>
        </div>

        {recommendationsLoading && (
          <p className="profile-hint"><LoaderCircle className="spin" size={15}/> Updating recommendations...</p>
        )}

        {recommendationsError && (
          <div className="profile-error" role="alert">{recommendationsError}</div>
        )}

        {!recommendationsLoading && recommendations && (
          <>
            <div className="recommendation-meta">
              <span>Goals: {recommendations.goals_used.join(", ")}</span>
              <span>{recommendations.recommendations.length} ranked foods</span>
            </div>

            {recommendations.recommendations.length === 0 ? (
              <p className="profile-hint">
                There are not enough comparable nutrient records in the current catalog to rank foods for these goals.
                Add more foods with relevant nutrient data or choose another goal.
              </p>
            ) : (
              <div className="recommendation-grid">
                {recommendations.recommendations.map(food => (
                  <article className="recommendation-card" key={food.food_id}>
                    <div className="recommendation-card-top">
                      <div>
                        <h3>{food.name}</h3>
                        <p>{food.category || "Food catalog"} · {food.source}</p>
                      </div>
                      <span className="recommendation-score">{food.score.toFixed(1)}<small>/100</small></span>
                    </div>

                    <div className="recommendation-score-track" aria-label={`Relative ranking score ${food.score} out of 100`}>
                      <span style={{ width: `${Math.max(0, Math.min(100, food.score))}%` }}/>
                    </div>

                    <div className="recommendation-reasons">
                      {food.reasons.map((reason, index) => (
                        <p key={`${food.food_id}-reason-${index}`}>{reason}</p>
                      ))}
                    </div>

                    <div className="recommendation-nutrients">
                      {food.nutrients_per_100g
                        .filter(nutrient => ["energy_kcal", "protein", "total_carbohydrate", "total_fat", "fiber", "total_sugars", "sodium"].includes(nutrient.key))
                        .map(nutrient => (
                          <div key={`${food.food_id}-${nutrient.key}`}>
                            <span>{nutrient.name}</span>
                            <strong>
                              {nutrient.amount_per_100g === null
                                ? "Not reported"
                                : `${Number(nutrient.amount_per_100g.toFixed(2))} ${nutrient.unit}`}
                            </strong>
                          </div>
                        ))}
                    </div>

                    <div className="recommendation-safety">
                      <span>{food.safety_screen.replaceAll("_", " ")}</span>
                      <p>{food.safety_note}</p>
                    </div>
                  </article>
                ))}
              </div>
            )}

            <div className="recommendation-limitations">
              <strong>How to interpret these results</strong>
              <p>{recommendations.method}</p>
              <ul>
                {recommendations.limitations.map(item => <li key={item}>{item}</li>)}
              </ul>
              {recommendations.excluded_known_conflicts > 0 && (
                <p>{recommendations.excluded_known_conflicts} catalog entries were excluded due to recorded conflicts.</p>
              )}
            </div>
          </>
        )}
      </section>
      <section className="profile-recipes">
        <div className="profile-heading">
          <span><ShieldCheck size={19}/></span>
          <div><h2>Recipe safety screening</h2><p>Check saved recipe ingredients against your profile.</p></div>
        </div>
        {recipes.length === 0 ? (
          <p className="profile-hint">Save a recipe first to check its recorded ingredients.</p>
        ) : recipes.map(recipe => {
          const result = checks[recipe.id];
          return (
            <article className="profile-recipe" key={recipe.id}>
              <div className="profile-recipe-top">
                <div><strong>{recipe.name}</strong><small>{recipe.ingredients.length} recorded ingredients</small></div>
                <button type="button" className="button button-secondary" disabled={checkingRecipe !== null} onClick={() => checkRecipe(recipe.id)}>
                  {checkingRecipe === recipe.id ? <LoaderCircle className="spin" size={15}/> : <ShieldCheck size={15}/>}
                  Check recipe
                </button>
              </div>
              {result && (
                <div className="profile-safety-result">
                  <strong className={result.status === "allergy_conflict" ? "safety-danger" : result.status === "no_known_conflict" ? "safety-neutral" : "safety-warning"}>
                    {result.status.replaceAll("_", " ")}
                  </strong>
                  {result.matches.map((match, index) => (
                    <p key={`${match.ingredient}-${index}`}><AlertTriangle size={14}/>{match.message}</p>
                  ))}
                  {result.matches.length === 0 && <p>No known conflicts were found in the recorded ingredients.</p>}
                  {result.unknown_ingredients.length > 0 && <p>Uncertain ingredients: {result.unknown_ingredients.join(", ")}</p>}
                  <small>{result.disclaimer}</small>
                </div>
              )}
            </article>
          );
        })}
      </section>
    </section>
  );
}
