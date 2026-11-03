const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type Nutrient = {
  nutrient_key: string; display_name: string; amount: number | null; unit: string; basis_g?: number;
};
export type Food = {
  id: number; name: string; category: string | null; source: string;
  external_id: string | null; source_url: string | null; nutrients: Nutrient[];
};
export type FoodSearchResult = {
  fdc_id: number | null; description: string | null; data_type?: string | null;
  brand_owner?: string | null; brand_name?: string | null; food_category?: string | null;
};
export type Recipe = {
  id: number; name: string; servings: number; instructions: string | null;
  ingredients: { id: number; food_id: number | null; ingredient_name: string; quantity: number; unit: string }[];
  nutrition_per_recipe: Nutrient[]; nutrition_per_serving: Nutrient[];
};
export type Recognition = {
  status: string; predicted_food: string | null; confidence: number | null;
  needs_review: boolean; model_version: string | null;
  top_predictions: { food_label: string; confidence: number }[]; message: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch { /* response did not contain JSON */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export const api = {
  localFoods: (q = "") => request<Food[]>(`/nutrition/foods${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  calculateFood: (id: number, grams: number) => request<{ food_id: number; food_name: string; quantity_g: number; nutrients: Nutrient[] }>(`/nutrition/foods/${id}/calculate?quantity_g=${grams}`),
  usdaSearch: (q: string) => request<{ query: string; count: number; results: FoodSearchResult[] }>(`/nutrition/foods/usda/search?q=${encodeURIComponent(q)}`),
  importUsda: (id: number) => request<Food>(`/nutrition/foods/usda/${id}/import`, { method: "POST" }),
  recipes: () => request<Recipe[]>("/recipes"),
  createRecipe: (payload: { name: string; servings: number; instructions?: string; ingredients: { food_id: number; quantity_g: number }[] }) =>
    request<Recipe>("/recipes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  recognize: (file: File) => {
    const data = new FormData(); data.append("file", file);
    return request<Recognition>("/recognition/predict", { method: "POST", body: data });
  },
};
