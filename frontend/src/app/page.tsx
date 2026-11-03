"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowDownRight, ArrowUpRight, BookOpen, Check, ChefHat, CircleHelp, Database, ImagePlus, LoaderCircle, Search, Sparkles, Utensils, X } from "lucide-react";
import { api, type Food, type FoodSearchResult, type Recipe, type Recognition } from "@/lib/api";

type Tab = "overview" | "nutrition" | "recognition" | "recipes";
const fmt = (value: number | null, unit: string) => value === null ? "Not reported" : `${Number(value).toFixed(2)} ${unit}`;
function Notice({ message, error = false, onClose }: { message: string; error?: boolean; onClose: () => void }) {
  return <div className={`notice ${error ? "notice-error" : ""}`} role="status">{error ? <CircleHelp size={17}/> : <Check size={17}/>}<span>{message}</span><button onClick={onClose} aria-label="Dismiss"><X size={16}/></button></div>;
}
function Metric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{unit}</small></div>;
}
export default function HomePage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [query, setQuery] = useState("");
  const [foods, setFoods] = useState<Food[]>([]);
  const [usda, setUsda] = useState<FoodSearchResult[]>([]);
  const [selectedFood, setSelectedFood] = useState<Food | null>(null);
  const [portionGrams, setPortionGrams] = useState(100);
  const [portionResult, setPortionResult] = useState<{food_name:string;quantity_g:number;nutrients:{nutrient_key:string;display_name:string;amount:number|null;unit:string}[]}|null>(null);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [recipeName, setRecipeName] = useState("");
  const [servings, setServings] = useState(2);
  const [ingredientFood, setIngredientFood] = useState("");
  const [quantity, setQuantity] = useState(100);
  const [ingredients, setIngredients] = useState<{food_id:number;quantity_g:number;name:string}[]>([]);
  const [image, setImage] = useState<File | null>(null);
  const [recognition, setRecognition] = useState<Recognition | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{message:string;error?:boolean}|null>(null);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  useEffect(() => {
    Promise.all([api.recipes(), api.localFoods()]).then(([saved, catalog]) => {
      setRecipes(saved); setFoods(catalog); setApiOnline(true);
    }).catch(() => setApiOnline(false));
  }, []);

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
    if (!image) return; setBusy(true); setRecognition(null);
    try { setRecognition(await api.recognize(image)); }
    catch(e) { setNotice({message:e instanceof Error ? e.message : "Recognition failed",error:true}); }
    finally { setBusy(false); }
  }
  async function loadRecipes() {
    try { setRecipes(await api.recipes()); } catch(e) { setNotice({message:e instanceof Error ? e.message : "Could not load recipes",error:true}); }
  }
  async function saveRecipe(event: React.FormEvent) {
    event.preventDefault();
    if (!recipeName.trim() || ingredients.length === 0) return;
    setBusy(true);
    try {
      await api.createRecipe({name:recipeName,servings,instructions:"",ingredients:ingredients.map(({food_id,quantity_g})=>({food_id,quantity_g}))});
      setRecipeName(""); setIngredients([]); await loadRecipes(); setNotice({message:"Recipe saved with calculated nutrition."});
    } catch(e) { setNotice({message:e instanceof Error ? e.message : "Recipe save failed",error:true}); }
    finally { setBusy(false); }
  }
  const nav: {id:Tab;label:string;icon:typeof Activity}[] = [
    {id:"overview",label:"Overview",icon:Activity},{id:"nutrition",label:"Nutrition",icon:Search},
    {id:"recognition",label:"Food scan",icon:ImagePlus},{id:"recipes",label:"Recipes",icon:ChefHat},
  ];

  return <main className="app-frame">
    <aside className="sidebar">
      <a className="brand" href="#"><span className="brand-mark">F</span><span>FoodInsight<span className="brand-accent">AI</span></span></a>
      <div className="workspace-label">WORKSPACE</div>
      <nav>{nav.map(item => <button key={item.id} className={`nav-item ${tab===item.id?"active":""}`} onClick={()=>setTab(item.id)}><item.icon size={18}/>{item.label}{tab===item.id&&<span className="nav-dot"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="api-indicator"><span className={apiOnline===true?"online":apiOnline===false?"offline":"pending"}/><span>{apiOnline===true?"API connected":apiOnline===false?"API unavailable":"Checking API"}</span></div><div className="sidebar-foot">FOODINSIGHTAI V2<br/>NUTRITION INTELLIGENCE</div></div>
    </aside>
    <section className="main-area">
      <header className="main-header"><div><span className="crumb">Workspace</span><span className="crumb-sep">/</span><strong>{nav.find(n=>n.id===tab)?.label}</strong></div><span className="header-tag"><span/> EVIDENCE-LED FOOD DATA</span></header>
      <div className="content">
        {notice&&<Notice message={notice.message} error={notice.error} onClose={()=>setNotice(null)}/>}
        {tab==="overview"&&<><section className="welcome"><div><p className="eyebrow">YOUR FOOD, UNDERSTOOD</p><h1>Make better sense<br/>of <em>every plate.</em></h1><p className="welcome-copy">A connected workspace for food recognition, nutrition facts, and recipe-level insights.</p><button className="button button-primary" onClick={()=>setTab("nutrition")}>Explore nutrition <ArrowUpRight size={16}/></button></div><div className="welcome-art"><div className="art-orbit orbit-one"/><div className="art-orbit orbit-two"/><div className="plate"><div className="plate-food"><span/><span/><span/><span/><span/></div></div><div className="art-label label-top"><Sparkles size={14}/> FOOD INTELLIGENCE</div><div className="art-label label-bottom"><span className="pulse"/> COMPOSITION · CONTEXT · CLARITY</div></div></section>
        <div className="section-title"><div><p className="eyebrow">YOUR TOOLKIT</p><h2>One workspace. Three ways in.</h2></div><span className="subtle">SELECT A WORKFLOW <ArrowDownRight size={14}/></span></div>
        <div className="workflow-grid">
          <button className="workflow-card card-scan" onClick={()=>setTab("recognition")}><span className="workflow-icon"><ImagePlus/></span><span className="workflow-number">01 / IDENTIFY</span><strong>Scan your food</strong><p>Upload a meal image and get model predictions with confidence-aware review.</p><span className="card-link">Open food scan <ArrowUpRight size={15}/></span></button>
          <button className="workflow-card" onClick={()=>setTab("nutrition")}><span className="workflow-icon"><Database/></span><span className="workflow-number">02 / EXPLORE</span><strong>Explore nutrition</strong><p>Search the local catalog and import attributed food composition data.</p><span className="card-link">Open nutrition <ArrowUpRight size={15}/></span></button>
          <button className="workflow-card" onClick={()=>setTab("recipes")}><span className="workflow-icon"><Utensils/></span><span className="workflow-number">03 / COMBINE</span><strong>Build a recipe</strong><p>Combine catalog ingredients and inspect estimated per-serving nutrients.</p><span className="card-link">Open recipes <ArrowUpRight size={15}/></span></button>
        </div>
        </>}
        {tab==="nutrition"&&<><div className="page-intro"><p className="eyebrow">FOOD COMPOSITION</p><h1>Nutrition <em>explorer.</em></h1><p>Search your local catalog and USDA FoodData Central. Import source records to use them in calculations.</p></div>
          <form className="search-form" onSubmit={searchFoods}><Search size={19}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search foods, e.g. cooked rice, idli, apple"/><button className="button button-primary" disabled={busy}>{busy?<LoaderCircle className="spin" size={16}/>: "Search"}</button></form>
          {selectedFood&&<section className="detail-panel"><div className="detail-heading"><div><p className="eyebrow">FOOD RECORD · {selectedFood.source.toUpperCase()}</p><h2>{selectedFood.name}</h2><p>{selectedFood.category??"Food composition record"} · Values per 100 g unless stated otherwise</p></div><div className="detail-actions"><button className="button button-secondary" onClick={()=>{setTab("recipes");setIngredientFood(String(selectedFood.id));}}>Use in recipe <ArrowUpRight size={14}/></button><button className="icon-button" onClick={()=>setSelectedFood(null)} aria-label="Close details"><X/></button></div></div><div className="portion-tool"><label>Portion size (g)<input type="number" min="1" max="100000" value={portionGrams} onChange={e=>setPortionGrams(Number(e.target.value))}/></label><button className="button button-secondary" onClick={async()=>{try{setPortionResult(await api.calculateFood(selectedFood.id,portionGrams));}catch(e){setNotice({message:e instanceof Error?e.message:"Calculation failed",error:true});}}}>Calculate portion</button></div><div className="nutrient-grid">{(portionResult?.nutrients??selectedFood.nutrients).map(n=><Metric key={n.nutrient_key} label={n.display_name} value={n.amount===null?"—":Number(n.amount).toFixed(2)} unit={n.amount===null?"Not reported":n.unit}/>)}</div>{proteinTotal&&<p className="source-note">Protein: {fmt(proteinTotal.amount,proteinTotal.unit)} per 100 g · Source: {selectedFood.source}</p>}{portionResult&&<p className="source-note">Calculated for {portionResult.quantity_g} g of {portionResult.food_name}.</p>}</section>}
          <div className="results-columns"><section><div className="list-heading"><h2>Local catalog</h2><span>{foods.length} results</span></div>{foods.length===0?<div className="empty-state"><Database/><p>Local results appear here.</p><small>Search above to find imported foods.</small></div>:foods.map(food=><button className="result-row" key={food.id} onClick={()=>setSelectedFood(food)}><span className="result-avatar"><Utensils/></span><span className="result-main"><strong>{food.name}</strong><small>{food.category??food.source}</small></span><ArrowUpRight size={16}/></button>)}</section>
          <section><div className="list-heading"><h2>USDA database</h2><span>{usda.length} results</span></div>{usda.length===0?<div className="empty-state"><BookOpen/><p>External results appear here.</p><small>Search USDA after entering a food.</small></div>:usda.map((item,i)=><div className="result-row remote-row" key={item.fdc_id??i}><span className="result-avatar"><BookOpen/></span><span className="result-main"><strong>{item.description??"Unnamed food"}</strong><small>{item.brand_owner??item.data_type??"USDA FoodData Central"}</small></span><button className="small-button" disabled={!item.fdc_id||busy} onClick={()=>item.fdc_id&&importFood(item.fdc_id)}>Import</button></div>)}</section></div>
        </>}
        {tab==="recognition"&&<><div className="page-intro"><p className="eyebrow">IMAGE ANALYSIS</p><h1>Food <em>recognition.</em></h1><p>Upload a clear image. Predictions below the confidence threshold are sent for human review.</p></div><div className="scan-layout"><section className="upload-panel"><label className="upload-zone"><input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{setImage(e.target.files?.[0]??null);setRecognition(null);}}/><span className="upload-symbol"><ImagePlus size={28}/></span><strong>{image?image.name:"Drop an image or browse"}</strong><small>JPG, PNG or WEBP · Max 10 MB</small></label>{image&&<div className="file-selected"><Check size={15}/> Image selected <button onClick={()=>setImage(null)}>Remove</button></div>}<button className="button button-primary full-button" onClick={runRecognition} disabled={!image||busy}>{busy?<LoaderCircle className="spin" size={16}/>:<Sparkles size={16}/>} Analyze image</button><p className="privacy-note">Images are validated by the API. Recognition requires a trained model artifact to be configured.</p></section><section className="scan-result">{recognition?<><p className="eyebrow">ANALYSIS RESULT</p><h2>{recognition.predicted_food??"Needs your review"}</h2><p>{recognition.message??"Model prediction returned."}</p><div className="confidence-row"><span>Top confidence</span><strong>{recognition.confidence===null?"—":`${(recognition.confidence*100).toFixed(1)}%`}</strong></div>{recognition.top_predictions.map((p,i)=><div className="prediction-row" key={`${p.food_label}-${i}`}><span>{p.food_label}</span><strong>{(p.confidence*100).toFixed(1)}%</strong><div className="confidence-track"><i style={{width:`${p.confidence*100}%`}}/></div></div>)}</>:<div className="empty-state tall"><ImagePlus/><h2>Your result will appear here.</h2><p>Model predictions include ranked candidates and a confidence-based review state.</p></div>}</section></div></>}
        {tab==="recipes"&&<><div className="page-intro"><p className="eyebrow">RECIPE WORKBENCH</p><h1>Build a <em>better plate.</em></h1><p>Choose foods already in your catalog, enter gram quantities, and calculate recipe totals.</p></div><div className="recipe-layout"><form className="recipe-form" onSubmit={saveRecipe}><h2>New recipe</h2><label>Recipe name<input required value={recipeName} onChange={e=>setRecipeName(e.target.value)} placeholder="e.g. Everyday breakfast bowl"/></label><label>Servings<input type="number" min="1" max="100" value={servings} onChange={e=>setServings(Number(e.target.value))}/></label><div className="ingredient-entry"><label>Catalog food<select value={ingredientFood} onChange={e=>setIngredientFood(e.target.value)}><option value="">Choose a food</option>{foods.map(food=><option key={food.id} value={food.id}>{food.name} · #{food.id}</option>)}</select></label><label>Quantity (g)<input type="number" min="1" value={quantity} onChange={e=>setQuantity(Number(e.target.value))}/></label></div><button type="button" className="button button-secondary" onClick={()=>{const food=foods.find(f=>f.id===Number(ingredientFood));if(food)setIngredients([...ingredients,{food_id:food.id,quantity_g:quantity,name:food.name}]);else setNotice({message:"Search or import a food in Nutrition before adding it.",error:true});}}>Add ingredient</button>
          {ingredients.length>0&&<div className="ingredient-list">{ingredients.map((item,i)=><div key={`${item.food_id}-${i}`}><span>{item.name}<small>{item.quantity_g} g</small></span><button type="button" onClick={()=>setIngredients(ingredients.filter((_,index)=>index!==i))} aria-label="Remove ingredient"><X size={15}/></button></div>)}</div>}
          <button className="button button-primary full-button" disabled={busy||ingredients.length===0}>{busy?<LoaderCircle className="spin" size={16}/>: "Save recipe and calculate"}</button></form>
          <section className="saved-recipes"><div className="list-heading"><h2>Saved recipes</h2><button className="text-button" onClick={loadRecipes}>Refresh</button></div>{recipes.length===0?<div className="empty-state"><ChefHat/><p>No recipes saved yet.</p><small>Build one from your imported catalog foods.</small></div>:recipes.map(recipe=><article className="saved-recipe" key={recipe.id}><div><span className="eyebrow">RECIPE · {recipe.servings} SERVINGS</span><h3>{recipe.name}</h3><p>{recipe.ingredients.map(i=>`${i.ingredient_name} (${i.quantity} ${i.unit})`).join(" · ")}</p></div><div className="recipe-nutrients">{recipe.nutrition_per_serving.slice(0,4).map(n=><span key={n.nutrient_key}><small>{n.display_name}</small><strong>{n.amount===null?"—":`${Number(n.amount).toFixed(1)} ${n.unit}`}</strong></span>)}</div></article>)}</section></div></>}
      </div>
      <footer className="main-footer"><span>FOODINSIGHTAI V2</span><span>Nutrition values retain their source and known limitations.</span></footer>
    </section>
  </main>;
}
