"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, ChefHat, CircleAlert, ClipboardList, LoaderCircle, Sparkles, UtensilsCrossed } from "lucide-react";
import {
  generateRecipeForStudio, RecipeStudioConflict, type RecipeStudioResult,
} from "@/lib/recipe-studio-request";
import type { FoodSafetyResult } from "@/lib/api";

export default function GenerateRecipePanel() {
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recipe, setRecipe] = useState<RecipeStudioResult | null>(null);
  const [conflict, setConflict] = useState<FoodSafetyResult | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const dish = title.trim();
    if (busy || dish.length < 2) return;
    setBusy(true);
    setError("");
    setRecipe(null);
    setConflict(null);
    try {
      setRecipe(await generateRecipeForStudio(dish));
    } catch (cause) {
      if (cause instanceof RecipeStudioConflict) {
        setConflict(cause.assessment);
        setError(cause.message);
      } else {
        setError(cause instanceof Error ? cause.message : "Recipe generation is temporarily unavailable.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="recipe-studio" aria-labelledby="recipe-studio-heading">
      <div className="recipe-studio-intro">
        <div className="recipe-studio-intro-icon" aria-hidden="true"><Sparkles size={21} /></div>
        <div>
          <div className="recipe-studio-overline">AI RECIPE STUDIO <span>EXPERIMENTAL</span></div>
          <h2 id="recipe-studio-heading">What would you like to cook?</h2>
          <p>Describe a dish and get an original cooking idea with an ingredient list and step-by-step preparation.</p>
        </div>
      </div>

      <div className="recipe-studio-grid">
        <form className="recipe-studio-form" onSubmit={submit}>
          <div className="recipe-studio-card-heading">
            <span className="recipe-studio-step">01</span>
            <div><h3>Your recipe idea</h3><p>Start with a dish name</p></div>
          </div>
          <label htmlFor="recipe-studio-dish">Dish name</label>
          <input
            id="recipe-studio-dish"
            type="text"
            minLength={2}
            maxLength={120}
            required
            autoComplete="off"
            placeholder="e.g. Vegetable pulao, paneer curry..."
            value={title}
            disabled={busy}
            onChange={event => setTitle(event.target.value)}
          />
          <p className="recipe-studio-field-hint">For best results, enter a specific dish. Check all ingredients and cooking instructions before use.</p>
          <button className="recipe-studio-submit" type="submit" disabled={busy || title.trim().length < 2}>
            {busy ? <><LoaderCircle className="spin" size={17} /> Generating recipe...</> : <><Sparkles size={17} /> Generate recipe <ArrowRight size={16} /></>}
          </button>
          {error && (
            <div className="recipe-studio-alert" role="alert">
              <CircleAlert size={18}/>
              <div><strong>{conflict ? "Recipe withheld due to a Food Profile conflict" : "Generation unavailable"}</strong>
                <p>{error}</p>
                {conflict && conflict.matches.length > 0 && (
                  <ul>{conflict.matches.map((match, index) =>
                    <li key={index}>{match.message}</li>
                  )}</ul>
                )}
                {conflict && <p>Choose a different dish or review your saved Food Profile. Do not assume an unlisted allergen is absent.</p>}
              </div>
            </div>
          )}
          <div className="recipe-studio-footnote"><CircleAlert size={15}/><span>The backend screens against your saved Food Profile when available, but cannot verify labels, hidden ingredients, cross-contact or allergen safety.</span></div>
        </form>

        <div className="recipe-studio-output" aria-live="polite" aria-busy={busy}>
          {busy ? (
            <div className="recipe-studio-placeholder">
              <div className="recipe-studio-placeholder-icon"><LoaderCircle className="spin" size={26}/></div>
              <h3>Preparing your recipe</h3>
              <p>The model is drafting ingredients and cooking steps. This may take a little time.</p>
            </div>
          ) : recipe ? (
            <article className="recipe-studio-result">
              <div className="recipe-studio-result-header">
                <div><div className="recipe-studio-overline">YOUR GENERATED RECIPE</div><h3>{recipe.title}</h3></div>
                <span className="recipe-studio-result-tag"><Sparkles size={13}/> AI DRAFT</span>
              </div>
              {recipe.safety && (
                <section className="recipe-studio-safety" aria-label="Personalized food safety screening">
                  <div className="recipe-studio-safety-heading"><CircleAlert size={18}/><strong>Food Profile screening</strong></div>
                  <p>{recipe.safety.status === "profile_missing"
                    ? "No saved Food Profile was found. Personalized restrictions were not applied."
                    : "Screened against saved restrictions. This does not establish allergen safety."}</p>
                  {recipe.safety.matches.length > 0 && (
                    <ul>{recipe.safety.matches.map((match, index) =>
                      <li key={index}>{match.message}</li>
                    )}</ul>
                  )}
                  <p>{recipe.safety.disclaimer}</p>
                </section>
              )}
              {(recipe.quality_warnings?.length ?? 0) > 0 && (
                <section className="recipe-studio-safety" aria-label="Recipe quality cautions">
                  <strong>Ingredient or preparation details to review</strong>
                  <ul>{recipe.quality_warnings!.map((message, index) => <li key={index}>{message}</li>)}</ul>
                </section>
              )}
              <div className="recipe-studio-result-body">
                <section className="recipe-studio-ingredients">
                  <div className="recipe-studio-section-title"><UtensilsCrossed size={18}/><h4>Ingredients</h4><span>{recipe.ingredients.length} items</span></div>
                  {recipe.ingredients.length > 0 ? <ul>{recipe.ingredients.map((ingredient, index) => <li key={index}><span className="recipe-studio-dot" aria-hidden="true"/>{ingredient}</li>)}</ul> : <p className="recipe-studio-empty">No structured ingredients were provided.</p>}
                </section>
                <section className="recipe-studio-method">
                  <div className="recipe-studio-section-title"><ClipboardList size={18}/><h4>Preparation steps</h4><span>{recipe.steps.length} steps</span></div>
                  {recipe.steps.length > 0 ? <ol>{recipe.steps.map((step, index) => <li key={index}><span className="recipe-studio-number">{String(index + 1).padStart(2, "0")}</span><span>{step}</span></li>)}</ol> : <p className="recipe-studio-empty">No structured preparation steps were provided.</p>}
                </section>
              </div>
              {(recipe.ingredients.length === 0 || recipe.steps.length === 0) && <pre className="recipe-studio-raw">{recipe.answer}</pre>}
              <div className="recipe-studio-result-footer"><CircleAlert size={16}/><span>{recipe.note} Review ingredients, proportions and cooking temperatures independently.</span></div>
            </article>
          ) : (
            <div className="recipe-studio-placeholder">
              <div className="recipe-studio-placeholder-icon"><ChefHat size={29}/></div>
              <h3>Your next recipe starts here</h3>
              <p>Enter a dish name on the left and your generated recipe will appear here, neatly organized.</p>
              <div className="recipe-studio-placeholder-lines" aria-hidden="true"><span/><span/><span/></div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
