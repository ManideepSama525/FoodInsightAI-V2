const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type Nutrient = {
  nutrient_key: string;
  display_name: string;
  amount: number | null;
  unit: string;
  basis_g?: number;
};

export type Food = {
  id: number;
  name: string;
  category: string | null;
  source: string;
  external_id: string | null;
  source_url: string | null;
  nutrients: Nutrient[];
};

export type FoodSearchResult = {
  fdc_id: number | null;
  description: string | null;
  data_type?: string | null;
  brand_owner?: string | null;
  brand_name?: string | null;
  food_category?: string | null;
};

export type Recipe = {
  id: number;
  name: string;
  servings: number;
  instructions: string | null;
  ingredients: {
    id: number;
    food_id: number | null;
    ingredient_name: string;
    quantity: number;
    unit: string;
  }[];
  nutrition_per_recipe: Nutrient[];
  nutrition_per_serving: Nutrient[];
};

export type Recognition = {
  status: string;
  predicted_food: string | null;
  confidence: number | null;
  needs_review: boolean;
  model_version: string | null;
  top_predictions: { food_label: string; confidence: number }[];
  message: string | null;
};

export type User = {
  id: number;
  email: string;
  display_name: string;
  is_active: boolean;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
};

export type DiaryEntry = {
  id: number;
  food_id: number;
  food_name: string;
  quantity_g: number;
  meal_type: "breakfast" | "lunch" | "dinner" | "snack";
  consumed_at: string;
  notes: string | null;
};

const TOKEN_KEY = "foodinsightai_access_token";

export const session = {
  getToken: () =>
    typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY),
  setToken: (token: string) => {
    if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
  },
  clear: () => {
    if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
  },
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = session.getToken();

  if (token) headers.set("Authorization", `Bearer ${token}`);

  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch {
      // Response did not contain JSON.
    }
    if (response.status === 401 && path !== "/auth/login") {
      session.clear();
      if (typeof window !== "undefined") window.dispatchEvent(new Event("foodinsightai:unauthorized"));
    }
    throw new Error(message);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  register: (payload: { email: string; password: string; display_name: string }) =>
    request<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  login: (payload: { email: string; password: string }) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  me: () => request<User>("/auth/me"),

  localFoods: (q = "") =>
    request<Food[]>(`/nutrition/foods${q ? `?q=${encodeURIComponent(q)}` : ""}`),

  calculateFood: (
    id: number,
    grams: number,
    quantitySource: "user_entered" | "estimated" = "user_entered",
  ) =>
    request<{
      food_id: number;
      food_name: string;
      quantity_g: number;
      quantity_source: "user_entered" | "estimated";
      quantity_note: string;
      nutrients: Nutrient[];
    }>(
      `/nutrition/foods/${id}/calculate?quantity_g=${grams}&quantity_source=${quantitySource}`,
    ),

  usdaSearch: (q: string) =>
    request<{ query: string; count: number; results: FoodSearchResult[] }>(
      `/nutrition/foods/usda/search?q=${encodeURIComponent(q)}`,
    ),

  importUsda: (id: number) =>
    request<Food>(`/nutrition/foods/usda/${id}/import`, { method: "POST" }),

  recipes: () => request<Recipe[]>("/recipes"),

  createRecipe: (payload: {
    name: string;
    servings: number;
    instructions?: string;
    ingredients: { food_id: number; quantity_g: number }[];
  }) =>
    request<Recipe>("/recipes", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  recognize: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<Recognition>("/recognition/predict", {
      method: "POST",
      body: data,
    });
  },

  diary: () => request<DiaryEntry[]>("/diary"),

  addDiaryEntry: (payload: {
    food_id: number;
    quantity_g: number;
    meal_type: DiaryEntry["meal_type"];
    notes?: string;
  }) =>
    request<DiaryEntry>("/diary", {
      method: "POST",
      body: JSON.stringify(payload),
    }),


  getFoodProfile: () => request<FoodProfile>("/food-profile"),

  updateFoodProfile: (payload: FoodProfile) =>
    request<FoodProfile>("/food-profile", {
      method: "PUT",
      body: JSON.stringify({
        allergies: payload.allergies,
        intolerances: payload.intolerances,
        dietary_preferences: payload.dietary_preferences,
        goals: payload.goals,
        disliked_foods: payload.disliked_foods,
        cuisine_interests: payload.cuisine_interests,
      }),
    }),

  readiness: () =>
    request<{ status: string; database: string; knowledge_graph: string }>("/system/readiness"),

  knowledgeGraphStatus: () =>
    request<{ enabled: boolean; connected: boolean; database: string }>("/knowledge-graph/status"),

  foodRecommendations: (limit = 10) =>
    request<FoodRecommendationResponse>(`/food-profile/recommendations?limit=${limit}`),
  assessRecipe: (id: number) =>
    request<FoodSafetyResult>(`/food-profile/recipes/${id}/assess`),

  assessIngredients: (ingredients: { name: string; confidence?: number }[]) =>
    request<FoodSafetyResult>("/food-profile/assess", {
      method: "POST",
      body: JSON.stringify({ ingredients }),
    }),
  deleteDiaryEntry: (id: number) =>
    request<void>(`/diary/${id}`, { method: "DELETE" }),
};
export type FoodConcern = {
  name: string;
  severity: "mild" | "moderate" | "severe" | "unspecified";
};

export type FoodProfile = {
  allergies: FoodConcern[];
  intolerances: FoodConcern[];
  dietary_preferences: string[];
  goals: string[];
  disliked_foods: string[];
  cuisine_interests: string[];
  updated_at?: string | null;
};

export type FoodSafetyMatch = {
  ingredient: string;
  concern: string;
  concern_type: string;
  severity: string;
  certainty: string;
  message: string;
};

export type FoodRecommendation = {
  food_id: number;
  name: string;
  category: string | null;
  source: string;
  score: number;
  reasons: string[];
  nutrients_per_100g: {
    key: string;
    name: string;
    amount_per_100g: number | null;
    unit: string;
    source: string;
  }[];
  safety_screen: string;
  safety_note: string;
};

export type FoodRecommendationResponse = {
  goals_used: string[];
  recommendations: FoodRecommendation[];
  excluded_known_conflicts: number;
  method: string;
  limitations: string[];
};
export type FoodSafetyResult = {
  status: string;
  safe_to_assume: boolean;
  matches: FoodSafetyMatch[];
  unknown_ingredients: string[];
  disclaimer: string;
};
