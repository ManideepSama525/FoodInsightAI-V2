"use client";
import Image from "next/image";
import AuthGate from "./AuthGate";
import GenerateRecipePanel from "@/components/GenerateRecipePanel";
import DiaryPanel from "./DiaryPanel";
import FoodFraudPanel from "./FoodFraudPanel";
import RegulatoryCompliancePanel from "./RegulatoryCompliancePanel";
import FoodProfilePanel from "./FoodProfilePanel";
import RagPanel from "./RagPanel";

import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowDownRight, ArrowUpRight, BookOpen, Check, ChefHat, CircleHelp, Database, ImagePlus, LoaderCircle, Search, ShieldCheck, Scale, Sparkles, Utensils, X } from "lucide-react";
import { api, type Food, type FoodSearchResult, type Recipe, type Recognition, type Nutrient, type FoodSafetyResult, type FreshnessPrediction } from "@/lib/api";

type Tab = "overview" | "nutrition" | "diary" | "recognition" | "recipes" | "profile" | "rag" | "fraud" | "regulatory";
const fmt = (value: number | null, unit: string) => value === null ? "Not reported" : `${Number(value).toFixed(2)} ${unit}`;
function Notice({ message, error = false, onClose }: { message: string; error?: boolean; onClose: () => void }) {
  return <div className={`notice ${error ? "notice-error" : ""}`} role="status">{error ? <CircleHelp size={17}/> : <Check size={17}/>}<span>{message}</span><button onClick={onClose} aria-label="Dismiss"><X size={16}/></button></div>;
}
function Metric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{unit}</small></div>;
}
const freshnessCategories = [
  "apple", "banana", "beef", "bellpepper", "bittergourd",
  "bittermelon", "capsicum", "carrot", "chicken", "cucumber",
  "eggplant", "fish_eye", "mackerel", "mango", "okra",
  "orange", "papaya", "pineapple", "potato", "silver_barb",
  "strawberry", "tilapia", "tomato", "tuna",
];
function WorkspacePage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [recipeMode, setRecipeMode] = useState<"saved" | "generate">("saved");
  const [query, setQuery] = useState("");
  const [foods, setFoods] = useState<Food[]>([]);
  const [usda, setUsda] = useState<FoodSearchResult[]>([]);
  const [selectedFood, setSelectedFood] = useState<Food | null>(null);
  const [portionGrams, setPortionGrams] = useState(100);
  const [portionSource, setPortionSource] = useState<"user_entered" | "estimated">("user_entered");
  const [portionResult, setPortionResult] = useState<{
    food_name: string;
    quantity_g: number;
    quantity_source: "user_entered" | "estimated";
    quantity_note: string;
    nutrients: { nutrient_key: string; display_name: string; amount: number | null; unit: string }[];
  } | null>(null);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [recipeName, setRecipeName] = useState("");
  const [servings, setServings] = useState(2);
  const [recipeInstructions, setRecipeInstructions] = useState("");
  const [recipeSafety, setRecipeSafety] = useState<FoodSafetyResult | null>(null);
  const [recipeSafetyLoading, setRecipeSafetyLoading] = useState(false);
  const [recipeSafetyAcknowledged, setRecipeSafetyAcknowledged] = useState(false);
  const [ingredientFood, setIngredientFood] = useState("");
  const [quantity, setQuantity] = useState(100);
  const [ingredients, setIngredients] = useState<{food_id:number;quantity_g:number;name:string}[]>([]);
  const [image, setImage] = useState<File | null>(null);
  const [recognition, setRecognition] = useState<Recognition | null>(null);
  const [foodScanSafety, setFoodScanSafety] = useState<Record<number, FoodSafetyResult>>({});
  const [foodScanSafetyLoading, setFoodScanSafetyLoading] = useState(false);
  const [foodScanSafetyErrors, setFoodScanSafetyErrors] = useState<Record<number, string>>({});
  const [recognitionModel, setRecognitionModel] = useState<"food101" | "indian">("indian");
  const [freshnessCategory, setFreshnessCategory] = useState("");
  const [freshness, setFreshness] = useState<FreshnessPrediction | null>(null);
  const [freshnessBusy, setFreshnessBusy] = useState(false);
  const [freshnessError, setFreshnessError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{message:string;error?:boolean}|null>(null);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [graphOnline, setGraphOnline] = useState<boolean | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [recipePreview, setRecipePreview] = useState<Nutrient[]>([]);
  const [recipePreviewLoading, setRecipePreviewLoading] = useState(false);
  const [recipePreviewError, setRecipePreviewError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    api.recipes().then(saved => {
      if (active) setRecipes(saved);
    }).catch(() => {
      if (active) setNotice({ message: "Saved recipes could not be loaded.", error: true });
    });

    api.localFoods().then(catalog => {
      if (active) setFoods(catalog);
    }).catch(() => {
      if (active) setNotice({ message: "The food catalog could not be loaded.", error: true });
    });

    api.readiness().then(result => {
      if (active) {
        setApiOnline(result.status === "ready" && result.database === "connected");
        setGraphOnline(result.knowledge_graph === "connected");
      }
    }).catch(() => {
      if (active) {
        setApiOnline(false);
        setGraphOnline(false);
      }
    });

    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!image) {
      setImagePreview(null);
      return;
    }

    const url = URL.createObjectURL(image);
    setImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  useEffect(() => {
    let active = true;

    async function calculateRecipePreview() {
      if (ingredients.length === 0 || servings < 1) {
        setRecipePreview([]);
        setRecipePreviewError(null);
        setRecipePreviewLoading(false);
        return;
      }

      setRecipePreviewLoading(true);
      setRecipePreviewError(null);

      try {
        const results = await Promise.all(
          ingredients.map(item => api.calculateFood(item.food_id, item.quantity_g))
        );

        if (!active) return;

        const totals = new Map<string, Nutrient>();

        for (const result of results) {
          for (const nutrient of result.nutrients) {
            const existing = totals.get(nutrient.nutrient_key);

            if (!existing) {
              totals.set(nutrient.nutrient_key, { ...nutrient });
            } else if (existing.amount !== null && nutrient.amount !== null) {
              existing.amount += nutrient.amount;
            } else {
              existing.amount = null;
            }
          }
        }

        const perServing = Array.from(totals.values()).map(item => ({
          ...item,
          amount: item.amount === null ? null : item.amount / servings,
        }));

        setRecipePreview(perServing);
      } catch (error) {
        if (!active) return;
        setRecipePreview([]);
        setRecipePreviewError(
          error instanceof Error
            ? `Nutrition preview unavailable: ${error.message}`
            : "Nutrition preview unavailable. Retry after checking the catalog."
        );
      } finally {
        if (active) setRecipePreviewLoading(false);
      }
    }

    void calculateRecipePreview();

    return () => { active = false; };
  }, [ingredients, servings]);

  useEffect(() => {
    if (tab === "recipes" && foods.length === 0) {
      api.localFoods().then(setFoods).catch(() => undefined);
    }
  }, [tab, foods.length]);
  const proteinTotal = useMemo(() => selectedFood?.nutrients.find(n => n.nutrient_key === "protein"), [selectedFood]);

  async function searchFoods(event: React.FormEvent) {
    event.preventDefault(); if (!query.trim()) return;
    setBusy(true); setSelectedFood(null);
    try { const [local, remote] = await Promise.all([api.localFoods(query), api.usdaSearch(query)]);
      setFoods(local); setUsda(remote.results); setNotice(null);
    } catch (e) { setNotice({message: e instanceof Error ? e.message : "Search failed", error:true}); }
    finally { setBusy(false); }
  }
  async function importFood(id: number) {
    setBusy(true);
    try { const food = await api.importUsda(id); setSelectedFood(food); setFoods(current => [food,...current.filter(f => f.id !== food.id)]); setNotice({message:`${food.name} added to your food catalog.`}); }
    catch(e) { setNotice({message:e instanceof Error ? e.message : "Import failed",error:true}); }
    finally { setBusy(false); }
  }
  async function runRecognition() {
    if (!image) return;

    setBusy(true);
    setRecognition(null);
    setFoodScanSafety({});
    setFoodScanSafetyErrors({});
    setFoodScanSafetyLoading(false);

    try {
      const result = await api.recognize(image, recognitionModel);
      setRecognition(result);

      // Do not assess unsupported or unconfirmed predictions.
      if (
        result.needs_review ||
        !result.predicted_food ||
        !result.associated_recipes?.length
      ) {
        return;
      }

      setFoodScanSafetyLoading(true);

      const assessments = await Promise.all(
        result.associated_recipes.map(async recipe => {
          const evidence = recipe.ingredients.map(ingredient => {
            const verifiedMapping =
              ingredient.food_id !== null &&
              ["exact_name", "approved_alias"].includes(ingredient.mapping_status);

            return {
              name: ingredient.ingredient_name,
              ...(verifiedMapping ? { confidence: 0.95 } : {}),
            };
          });

          if (evidence.length === 0) {
            return {
              recipeId: recipe.recipe_id,
              error: "This recipe has no ingredient records to assess.",
            };
          }

          try {
            const assessment = await api.assessIngredients(evidence);
            return { recipeId: recipe.recipe_id, assessment };
          } catch (error) {
            return {
              recipeId: recipe.recipe_id,
              error: error instanceof Error
                ? error.message
                : "Ingredient safety assessment failed.",
            };
          }
        })
      );

      const safetyResults: Record<number, FoodSafetyResult> = {};
      const safetyErrors: Record<number, string> = {};

      for (const item of assessments) {
        if ("assessment" in item && item.assessment) {
          safetyResults[item.recipeId] = item.assessment;
        } else if ("error" in item && item.error) {
          safetyErrors[item.recipeId] = item.error;
        }
      }

      setFoodScanSafety(safetyResults);
      setFoodScanSafetyErrors(safetyErrors);
    } catch (error) {
      setNotice({
        message: error instanceof Error ? error.message : "Recognition failed.",
        error: true,
      });
    } finally {
      setBusy(false);
      setFoodScanSafetyLoading(false);
    }
  }
  async function runFreshness() {
    if (!image || !freshnessCategory) return;

    setFreshnessBusy(true);
    setFreshness(null);
    setFreshnessError(null);

    try {
      setFreshness(await api.predictFreshness(image, freshnessCategory));
    } catch (e) {
      setFreshnessError(
        e instanceof Error ? e.message : "Freshness analysis failed."
      );
    } finally {
      setFreshnessBusy(false);
    }
  }
  async function loadRecipes() {
    try { setRecipes(await api.recipes()); } catch(e) { setNotice({message:e instanceof Error ? e.message : "Could not load recipes",error:true}); }
  }
  async function saveRecipe(event: React.FormEvent) {
    event.preventDefault();
    if (!recipeName.trim() || ingredients.length === 0) return;

    if (!recipeSafety) {
      setRecipeSafetyLoading(true);
      try {
        const result = await api.assessIngredients(
          ingredients.map(item => ({ name: item.name, confidence: 1.0 }))
        );
        setRecipeSafety(result);
        setRecipeSafetyAcknowledged(false);
        setNotice({ message: "Ingredient screening completed. Review the result before saving." });
      } catch (e) {
        setNotice({
          message: e instanceof Error ? e.message : "Ingredient screening failed. Recipe was not saved.",
          error: true
        });
      } finally {
        setRecipeSafetyLoading(false);
      }
      return;
    }

    if (!recipeSafetyAcknowledged) return;

    setBusy(true);
    try {
      await api.createRecipe({
        name: recipeName.trim(),
        servings,
        instructions: recipeInstructions.trim(),
        ingredients: ingredients.map(({ food_id, quantity_g }) => ({ food_id, quantity_g }))
      });
      setRecipeName("");
      setRecipeInstructions("");
      setIngredients([]);
      setRecipeSafety(null);
      setRecipeSafetyAcknowledged(false);
      await loadRecipes();
      setNotice({ message: "Recipe saved with calculated nutrition." });
    } catch (e) {
      setNotice({
        message: e instanceof Error ? e.message : "Recipe save failed",
        error: true
      });
    } finally {
      setBusy(false);
    }
  }
  const nav: {id:Tab;label:string;icon:typeof Activity}[] = [
    {id:"overview",label:"Overview",icon:Activity},{id:"nutrition",label:"Nutrition",icon:Search},
    {id:"diary",label:"Food diary",icon:BookOpen},{id:"rag",label:"Food intelligence",icon:Sparkles},{id:"recognition",label:"Food scan",icon:ImagePlus},{id:"recipes",label:"Recipes",icon:ChefHat},{id:"fraud",label:"Food fraud",icon:ShieldCheck},{id:"regulatory",label:"Regulatory compliance",icon:Scale},{id:"profile",label:"Food profile",icon:Activity},
  ];

  return <main className="app-frame">
    <aside className="sidebar">
      <a className="brand" href="#"><span className="brand-mark">F</span><span>FoodInsight<span className="brand-accent">AI</span></span></a>
      <div className="workspace-label">WORKSPACE</div>
      <nav>{nav.map(item => <button key={item.id} aria-current={tab === item.id ? "page" : undefined} className={`nav-item ${tab===item.id?"active":""}`} onClick={()=>setTab(item.id)}><item.icon size={18}/>{item.label}{tab===item.id&&<span className="nav-dot"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="api-indicator"><span className={apiOnline===true?"online":apiOnline===false?"offline":"pending"}/><span>{apiOnline===true?"API connected":apiOnline===false?"API unavailable":"Checking API"}</span></div><div className="sidebar-foot">FOODINSIGHTAI V2<br/>NUTRITION INTELLIGENCE<br/><span className={graphOnline===true?"graph-online":graphOnline===false?"graph-offline":"graph-pending"}>KNOWLEDGE GRAPH: {graphOnline===true?"CONNECTED":graphOnline===false?"UNAVAILABLE":"CHECKING"}</span></div></div>
    </aside>
    <section className="main-area">
      <header className="main-header"><div><span className="crumb">Workspace</span><span className="crumb-sep">/</span><strong>{nav.find(n=>n.id===tab)?.label}</strong></div><span className="header-tag"><span/> EVIDENCE-LED FOOD DATA</span></header>
      <div className="content">
        {notice&&<Notice message={notice.message} error={notice.error} onClose={()=>setNotice(null)}/>}
        {tab==="overview"&&<><section className="welcome"><div><p className="eyebrow">YOUR FOOD, UNDERSTOOD</p><h1>Make better sense<br/>of <em>every plate.</em></h1><p className="welcome-copy">A connected workspace for food recognition, nutrition facts, and recipe-level insights.</p><button className="button button-primary" onClick={()=>setTab("nutrition")}>Explore nutrition <ArrowUpRight size={16}/></button></div><div className="welcome-art"><div className="art-orbit orbit-one"/><div className="art-orbit orbit-two"/><div className="plate"><div className="plate-food"><span/><span/><span/><span/><span/></div></div><div className="art-label label-top"><Sparkles size={14}/> FOOD INTELLIGENCE</div><div className="art-label label-bottom"><span className="pulse"/> COMPOSITION Â· CONTEXT Â· CLARITY</div></div></section>
        <div className="section-title"><div><p className="eyebrow">YOUR TOOLKIT</p><h2>One workspace. Three ways in.</h2></div><span className="subtle">SELECT A WORKFLOW <ArrowDownRight size={14}/></span></div>
        <div className="workflow-grid">
          <button className="workflow-card card-scan" onClick={()=>setTab("recognition")}><span className="workflow-icon"><ImagePlus/></span><span className="workflow-number">01 / IDENTIFY</span><strong>Scan your food</strong><p>Upload a meal image and get model predictions with confidence-aware review.</p><span className="card-link">Open food scan <ArrowUpRight size={15}/></span></button>
          <button className="workflow-card" onClick={()=>setTab("nutrition")}><span className="workflow-icon"><Database/></span><span className="workflow-number">02 / EXPLORE</span><strong>Explore nutrition</strong><p>Search the local catalog and import attributed food composition data.</p><span className="card-link">Open nutrition <ArrowUpRight size={15}/></span></button>
          <button className="workflow-card" onClick={()=>setTab("recipes")}><span className="workflow-icon"><Utensils/></span><span className="workflow-number">03 / COMBINE</span><strong>Build a recipe</strong><p>Combine catalog ingredients and inspect estimated per-serving nutrients.</p><span className="card-link">Open recipes <ArrowUpRight size={15}/></span></button>
        </div>
        </>}
        {tab==="nutrition"&&<><div className="page-intro"><p className="eyebrow">FOOD COMPOSITION</p><h1>Nutrition <em>explorer.</em></h1><p>Search your local catalog and USDA FoodData Central. Import source records to use them in calculations.</p></div>
          <form className="search-form" onSubmit={searchFoods}><Search size={19}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search foods, e.g. cooked rice, idli, apple"/><button className="button button-primary" disabled={busy}>{busy?<LoaderCircle className="spin" size={16}/>: "Search"}</button></form>
          {selectedFood&&<section className="detail-panel"><div className="detail-heading"><div><p className="eyebrow">FOOD RECORD Â· {selectedFood.source.toUpperCase()}</p><h2>{selectedFood.name}</h2><p>{selectedFood.category??"Food composition record"} Â· Values per 100 g unless stated otherwise</p></div><div className="detail-actions"><button className="button button-secondary" onClick={()=>{setTab("recipes");setIngredientFood(String(selectedFood.id));}}>Use in recipe <ArrowUpRight size={14}/></button><button className="icon-button" onClick={()=>setSelectedFood(null)} aria-label="Close details"><X/></button></div></div><div className="portion-tool">
  <label>
    Portion size (g)
    <input
      type="number"
      min="1"
      max="100000"
      value={portionGrams}
      onChange={e => {
        setPortionGrams(Number(e.target.value));
        setPortionResult(null);
      }}
    />
  </label>
  <label>
    Quantity basis
    <select
      value={portionSource}
      onChange={e => {
        setPortionSource(e.target.value as "user_entered" | "estimated");
        setPortionResult(null);
      }}
    >
      <option value="user_entered">Entered by me</option>
      <option value="estimated">Approximate estimate</option>
    </select>
  </label>
  <button
    className="button button-secondary"
    disabled={!Number.isFinite(portionGrams) || portionGrams <= 0 || portionGrams > 100000}
    onClick={async () => {
      try {
        setPortionResult(
          await api.calculateFood(selectedFood.id, portionGrams, portionSource)
        );
      } catch (e) {
        setNotice({
          message: e instanceof Error ? e.message : "Calculation failed",
          error: true,
        });
      }
    }}
  >
    Calculate portion
  </button>
</div>
<div className="nutrient-grid">
  {(portionResult?.nutrients ?? selectedFood.nutrients).map(n => (
    <Metric
      key={n.nutrient_key}
      label={n.display_name}
      value={n.amount === null ? "â€”" : Number(n.amount).toFixed(2)}
      unit={n.amount === null ? "Not reported" : n.unit}
    />
  ))}
</div>
{proteinTotal && (
  <p className="source-note">
    Protein: {fmt(proteinTotal.amount, proteinTotal.unit)} per 100 g Â· Source: {selectedFood.source}
  </p>
)}
{portionResult && (
  <p className="source-note">
    Calculated for {portionResult.quantity_g} g of {portionResult.food_name}.
    {" "}{portionResult.quantity_note}
  </p>
)}
</section>}
          <div className="results-columns"><section><div className="list-heading"><h2>Local catalog</h2><span>{foods.length} results</span></div>{foods.length===0?<div className="empty-state"><Database/><p>Local results appear here.</p><small>Search above to find imported foods.</small></div>:foods.map(food=><button className="result-row" key={food.id} onClick={()=>{setSelectedFood(food);setPortionResult(null);}}><span className="result-avatar"><Utensils/></span><span className="result-main"><strong>{food.name}</strong><small>{food.category??food.source}</small></span><ArrowUpRight size={16}/></button>)}</section>
          <section><div className="list-heading"><h2>USDA database</h2><span>{usda.length} results</span></div>{usda.length===0?<div className="empty-state"><BookOpen/><p>External results appear here.</p><small>Search USDA after entering a food.</small></div>:usda.map((item,i)=><div className="result-row remote-row" key={item.fdc_id??i}><span className="result-avatar"><BookOpen/></span><span className="result-main"><strong>{item.description??"Unnamed food"}</strong><small>{item.brand_owner??item.data_type??"USDA FoodData Central"}</small></span><button className="small-button" disabled={!item.fdc_id||busy} onClick={()=>item.fdc_id&&importFood(item.fdc_id)}>Import</button></div>)}</section></div>
        </>}
        {tab==="fraud"&&<FoodFraudPanel />}
        {tab==="regulatory"&&<RegulatoryCompliancePanel />}
        {tab==="diary"&&<DiaryPanel />}
        {tab==="profile"&&<FoodProfilePanel recipes={recipes} />}
        {tab==="rag"&&<RagPanel />}
        {tab==="recognition"&&<><div className="page-intro"><p className="eyebrow">IMAGE ANALYSIS</p><h1>Food <em>recognition.</em></h1><p>Upload a clear image. Predictions below the confidence threshold are sent for human review.</p></div><div className="scan-layout"><section className="upload-panel"><label className="field-label" htmlFor="recognition-model">Recognition model</label><select id="recognition-model" value={recognitionModel} onChange={e=>{setRecognitionModel(e.target.value as "food101" | "indian");setRecognition(null);setFoodScanSafety({});setFoodScanSafetyErrors({});}}><option value="indian">Indian foods Â· 15 classes</option><option value="food101">Food-101 Â· 101 classes</option></select><label className="field-label" htmlFor="freshness-category">Freshness category (optional)</label><select id="freshness-category" value={freshnessCategory} onChange={e=>{setFreshnessCategory(e.target.value);setFreshness(null);setFreshnessError(null);}}><option value="">Skip freshness analysis</option>{freshnessCategories.map(category=><option key={category} value={category}>{category.replace(/_/g," ")}</option>)}</select><button type="button" className="button button-secondary full-button" onClick={runFreshness} disabled={!image||!freshnessCategory||freshnessBusy}>{freshnessBusy?<LoaderCircle className="spin" size={16}/>:<Activity size={16}/>} Check freshness</button><p className="privacy-note">Select the actual food category before checking freshness. This analysis is independent of food recognition.</p>

<label className="upload-zone"><input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{setImage(e.target.files?.[0]??null);setRecognition(null);setFoodScanSafety({});setFoodScanSafetyErrors({});setFreshness(null);setFreshnessError(null);}}/><span className="upload-symbol"><ImagePlus size={28}/></span><strong>{image?image.name:"Drop an image or browse"}</strong><small>JPG, PNG or WEBP Â· Max 10 MB</small></label>{imagePreview&&<div className="image-preview"><Image src={imagePreview} alt="Selected food for recognition" width={640} height={480} unoptimized style={{width:"auto",height:"auto",maxWidth:"100%",maxHeight:"300px"}}/></div>}{image&&<div className="file-selected"><Check size={15}/> Image selected <button onClick={()=>{setImage(null);setRecognition(null);setFoodScanSafety({});setFoodScanSafetyErrors({});setFreshness(null);setFreshnessError(null);}}>Remove</button></div>}<button className="button button-primary full-button" onClick={runRecognition} disabled={!image||busy}>{busy?<LoaderCircle className="spin" size={16}/>:<Sparkles size={16}/>} Analyze image</button><p className="privacy-note">Images are validated by the API. Recognition requires a trained model artifact to be configured.</p></section><section className="scan-result">{recognition?<><p className="eyebrow">ANALYSIS RESULT</p><h2>{recognition.predicted_food??"Needs your review"}</h2><p>{recognition.message??"Model prediction returned."}</p><div className="confidence-row"><span>Top confidence</span><strong>{recognition.confidence===null?"â€”Â":`${(recognition.confidence*100).toFixed(1)}%`}</strong></div>{recognition.top_predictions.map((p,i)=><div className="prediction-row" key={`${p.food_label}-${i}`}><span>{p.food_label}</span><strong>{(p.confidence*100).toFixed(1)}%</strong><div className="confidence-track"><i style={{width:`${p.confidence*100}%`}}/></div></div>)}{recognition.needs_review ? <section className="recipe-preview" aria-live="polite"><h3>HUMAN REVIEW REQUIRED</h3><p className="preview-note">This prediction has not been confirmed. Dish matching and recipe-associated ingredients are withheld until the prediction is reviewed.</p></section> : <>{recognition.canonical_dish_name&&<div className="recipe-preview"><h3>Knowledge Graph dish</h3><p>{recognition.canonical_dish_name}</p></div>}<section className="recipe-preview"><h3>RECIPE-ASSOCIATED INGREDIENTS</h3><p className="preview-note">These ingredients come from linked recipe records. They were not detected in the uploaded image. Their mapping and quantity statuses are shown for transparency; this Food Scan display does not calculate nutrition from them.</p>{recognition.associated_recipes?.length?recognition.associated_recipes.map(recipe=><article key={recipe.recipe_id} className="saved-recipe"><div><h3>{recipe.recipe_name}</h3><small>{recipe.servings} servings Â· {recipe.source_attribution??recipe.source??recipe.association_source}</small></div>{recipe.ingredients.length?<div className="ingredient-list">{recipe.ingredients.map((ingredient,index)=><div key={`${recipe.recipe_id}-${index}`}><span><strong>{ingredient.ingredient_name}</strong><small>{ingredient.quantity===null?"Quantity not specified":`${ingredient.quantity} ${ingredient.unit??""}`} Â· Mapping: {ingredient.mapping_status} Â· Quantity: {ingredient.quantity_status}</small></span></div>)}</div>:<p className="preview-note">No ingredient records are available for this recipe.</p>}{recipe.source_url&&<a href={recipe.source_url} target="_blank" rel="noreferrer">Recipe source</a>}</article>):<p className="preview-note">No curated public recipe is currently associated with this dish. Ingredients have not been inferred from the image.</p>}</section></>}</>:<div className="empty-state tall"><ImagePlus/><h2>Your result will appear here.</h2><p>Model predictions include ranked candidates and a confidence-based review state.</p></div>}{recognition && <section className="recipe-preview" aria-live="polite">
  <h3>PERSONALIZED FOOD SAFETY SCREENING</h3>
  {recognition.needs_review ? (
    <p className="preview-note">
      Safety assessment is withheld because this prediction requires human review.
    </p>
  ) : !recognition.predicted_food ? (
    <p className="preview-note">
      No supported food class was returned. No personalized assessment was performed.
    </p>
  ) : !recognition.associated_recipes?.length ? (
    <p className="preview-note">
      No curated recipe is associated with this recognized dish. Ingredient safety cannot be assessed.
    </p>
  ) : (
    <>
      <p className="preview-note">
        Each curated recipe is assessed separately against your saved food profile.
        Ingredients are sourced from recipe records, not detected from the image.
      </p>
      {recognition.associated_recipes.map(recipe => {
        const assessment = foodScanSafety[recipe.recipe_id];
        const assessmentError = foodScanSafetyErrors[recipe.recipe_id];
        const statusLabel = assessment?.status === "allergy_conflict"
          ? "AVOID — ALLERGY CONFLICT"
          : assessment?.status === "preference_conflict"
            ? "CAUTION — PROFILE CONFLICT"
            : assessment?.status === "insufficient_evidence"
              ? "INSUFFICIENT DATA"
              : assessment?.status === "profile_missing"
                ? "INSUFFICIENT DATA — PROFILE NOT SET UP"
                : assessment?.status === "no_known_conflict"
                  ? "NO KNOWN CONFLICT IN AVAILABLE INGREDIENTS"
                  : assessment?.status?.replace(/_/g, " ").toUpperCase() ?? "ASSESSMENT PENDING";

        return (
          <article className="saved-recipe" key={`safety-${recipe.recipe_id}`}>
            <div className="list-heading">
              <h3>{recipe.recipe_name}</h3>
              <strong>{foodScanSafetyLoading && !assessment && !assessmentError
                ? "Assessing..."
                : statusLabel}</strong>
            </div>

            {assessmentError && (
              <p className="preview-note" role="alert">{assessmentError}</p>
            )}

            {assessment?.matches?.length ? (
              <div className="ingredient-list">
                {assessment.matches.map((match, index) => (
                  <div key={`${match.ingredient}-${match.concern}-${index}`}>
                    <span>
                      <strong>{match.ingredient}</strong>
                      <small>
                        {match.concern_type.replace(/_/g, " ")} · {match.concern} · {match.severity}
                      </small>
                      <small>{match.message}</small>
                      <small>Evidence: {match.certainty.replace(/_/g, " ")}</small>
                    </span>
                  </div>
                ))}
              </div>
            ) : assessment && (
              <p className="preview-note">
                No matching conflicts were identified in the assessed ingredients.
              </p>
            )}

            {assessment?.unknown_ingredients?.length ? (
              <p className="preview-note">
                Ingredients requiring further verification: {assessment.unknown_ingredients.join(", ")}
              </p>
            ) : null}

            {assessment && (
              <p className="preview-note">{assessment.disclaimer}</p>
            )}
          </article>
        );
      })}
      <p className="preview-note">
        This is a screening aid, not a medical safety guarantee. Recipe records may be incomplete.
        Cross-contact, hidden ingredients, processing aids, substitutions, and preparation
        differences are not verified. Confirm ingredients with the food provider or packaging,
        especially when you have a severe allergy. “No known conflict” does not mean “safe.”
      </p>
    </>
  )}
</section>}
{freshnessError && <section className="recipe-preview" role="alert"><h3>FRESHNESS ANALYSIS FAILED</h3><p>{freshnessError}</p></section>}{freshness && <section className="recipe-preview" aria-live="polite"><h3>FOOD FRESHNESS RESULT</h3><div className="confidence-row"><span>Category</span><strong>{freshness.category}</strong></div><div className="confidence-row"><span>Predicted condition</span><strong>{freshness.predicted_label}</strong></div><div className="confidence-row"><span>Confidence</span><strong>{(freshness.confidence*100).toFixed(1)}%</strong></div><h3>CLASS PROBABILITIES</h3>{Object.entries(freshness.probabilities).map(([label,probability])=><div className="prediction-row" key={label}><span>{label}</span><strong>{(probability*100).toFixed(1)}%</strong><div className="confidence-track"><i style={{width:`${probability*100}%`}}/></div></div>)}<p className="preview-note">{freshness.safety_notice}</p><small>Model: {freshness.model_version} · Device: {freshness.device}</small></section>}

</section></div></>}
        {tab==="recipes"&&<><div className="page-intro"><p className="eyebrow">RECIPE WORKBENCH</p><h1>Build a <em>better plate.</em></h1><p>Choose foods already in your catalog, enter gram quantities, or create a new cooking idea with AI.</p></div><div className="recipe-mode-switch" role="tablist" aria-label="Recipe workspace view"><button type="button" role="tab" className="recipe-mode-button" aria-selected={recipeMode==="saved"} onClick={()=>setRecipeMode("saved")}><ChefHat size={16}/> My recipes</button><button type="button" role="tab" className="recipe-mode-button" aria-selected={recipeMode==="generate"} onClick={()=>setRecipeMode("generate")}><Sparkles size={16}/> Generate a recipe</button></div>{recipeMode==="saved" && <div className="recipe-layout"><form className="recipe-form" onSubmit={saveRecipe}><h2>New recipe</h2><label>Recipe name<input required value={recipeName} onChange={e=>setRecipeName(e.target.value)} placeholder="e.g. Everyday breakfast bowl"/></label><label>Servings<input type="number" min="1" max="100" value={servings} onChange={e=>setServings(Number(e.target.value))}/></label>
          <label>Preparation instructions<textarea rows={4} maxLength={5000} value={recipeInstructions} onChange={e=>setRecipeInstructions(e.target.value)} placeholder="Describe how to prepare this recipe (optional)."/></label><div className="ingredient-entry"><label>Catalog food<select value={ingredientFood} onChange={e=>setIngredientFood(e.target.value)}><option value="">Choose a food</option>{foods.map(food=><option key={food.id} value={food.id}>{food.name} Â· #{food.id}</option>)}</select></label><label>Quantity (g)<input type="number" min="1" value={quantity} onChange={e=>setQuantity(Number(e.target.value))}/></label></div><button type="button" className="button button-secondary" onClick={()=>{const food=foods.find(f=>f.id===Number(ingredientFood));if(food) {
             setIngredients([...ingredients,{food_id:food.id,quantity_g:quantity,name:food.name}]);
             setRecipeSafety(null);
             setRecipeSafetyAcknowledged(false);
           }else setNotice({message:"Search or import a food in Nutrition before adding it.",error:true});}}>Add ingredient</button>
          {ingredients.length>0&&<div className="ingredient-list">{ingredients.map((item,i)=><div key={`${item.food_id}-${i}`}><span>{item.name}<small>{item.quantity_g} g</small></span><button type="button" onClick={()=>{setIngredients(ingredients.filter((_,index)=>index!==i));setRecipeSafety(null);setRecipeSafetyAcknowledged(false);}} aria-label="Remove ingredient"><X size={15}/></button></div>)}</div>}
          {recipeSafety && <section className="recipe-preview" aria-live="polite">
             <div className="list-heading">
               <h3>Ingredient safety screening</h3>
               <strong>{recipeSafety.status.replace(/_/g, " ")}</strong>
             </div>
             {recipeSafety.matches.length > 0 ? (
               <div className="ingredient-list">
                 {recipeSafety.matches.map((match, index) => (
                   <div key={`${match.ingredient}-${index}`}>
                     <span>
                       <strong>{match.ingredient}</strong>
                       <small>{match.concern} ? {match.severity} ? {match.certainty}</small>
                       <small>{match.message}</small>
                     </span>
                   </div>
                 ))}
               </div>
             ) : <p className="preview-note">No known conflicts were identified by this screening.</p>}
             {recipeSafety.unknown_ingredients.length > 0 &&
               <p className="preview-note">
                 Ingredients requiring further review: {recipeSafety.unknown_ingredients.join(", ")}
               </p>}
             <p className="preview-note">{recipeSafety.disclaimer}</p>
             <p className="preview-note">This screening is not a medical safety guarantee. Cross-contact and hidden ingredients may not be assessed.</p>
             <label>
               <input
                 type="checkbox"
                 checked={recipeSafetyAcknowledged}
                 onChange={e => setRecipeSafetyAcknowledged(e.target.checked)}
               />
               I have reviewed this screening and understand its limitations.
             </label>
           </section>}
                     {ingredients.length > 0 && <section className="recipe-preview">
            <div className="list-heading">
              <h3>Estimated nutrition per serving</h3>
              <span>{recipePreviewLoading ? "Calculating..." : `${servings} servings`}</span>
            </div>
            {recipePreviewLoading ? <p className="preview-note">Updating ingredient calculations...</p> :
              recipePreviewError ? <p className="preview-note" role="alert">{recipePreviewError}</p> :
              recipePreview.length === 0 ? <p className="preview-note">No nutrient values are available for these ingredients.</p> :
              <div className="recipe-nutrients">
                {recipePreview.map(n => <span key={n.nutrient_key}>
                  <small>{n.display_name}</small>
                  <strong>{n.amount === null ? "Not reported" : `${n.amount.toFixed(2)} ${n.unit}`}</strong>
                </span>)}
              </div>
            }
            <p className="preview-note">Calculated from catalog records. Missing nutrient values remain unreported.</p>
          </section>}
          <button className="button button-primary full-button" disabled={busy || recipeSafetyLoading || ingredients.length===0 || (recipeSafety !== null && !recipeSafetyAcknowledged)}>
             {busy || recipeSafetyLoading
               ? <LoaderCircle className="spin" size={16}/>
               : recipeSafety
                 ? "Save recipe and calculate"
                 : "Check ingredients before saving"}
           </button></form>
          <section className="saved-recipes"><div className="list-heading"><h2>Saved recipes</h2><button className="text-button" onClick={loadRecipes}>Refresh</button></div>{recipes.length===0?<div className="empty-state"><ChefHat/><p>No recipes saved yet.</p><small>Build one from your imported catalog foods.</small></div>:recipes.map(recipe=><article className="saved-recipe" key={recipe.id}><div><span className="eyebrow">RECIPE Â· {recipe.servings} SERVINGS</span><h3>{recipe.name}</h3>{recipe.instructions && <p className="preview-note">{recipe.instructions}</p>}<p>{recipe.ingredients.map(i=>`${i.ingredient_name} (${i.quantity} ${i.unit})`).join(" Â· ")}</p></div><div className="recipe-nutrients">{recipe.nutrition_per_serving.slice(0,4).map(n=><span key={n.nutrient_key}><small>{n.display_name}</small><strong>{n.amount===null?"â€”Â":`${Number(n.amount).toFixed(1)} ${n.unit}`}</strong></span>)}</div></article>)}</section></div>}{recipeMode==="generate" && <GenerateRecipePanel />}</>}
      </div>
      <footer className="main-footer"><span>FOODINSIGHTAI V2</span><span>Nutrition values retain their source and known limitations.</span></footer>
    </section>
  </main>;
}


export default function HomePage() {
  return <AuthGate><WorkspacePage /></AuthGate>;
}


