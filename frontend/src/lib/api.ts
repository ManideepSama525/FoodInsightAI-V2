
export type GeneratedRecipeResult = {
  title: string; answer: string; ingredients: string[]; steps: string[];
  model: string; adapter?: string | null; note: string;
};

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

export type RecognizedIngredient = {
  ingredient_name: string;
  food_id: number | null;
  quantity: number | null;
  unit: string | null;
  mapping_status: string;
  quantity_status: string;
};
export type AssociatedRecipe = {
  recipe_id: number;
  recipe_name: string;
  servings: number;
  source: string | null;
  source_url: string | null;
  source_attribution: string | null;
  association_source: string;
  association_provenance: Record<string, unknown>;
  ingredients: RecognizedIngredient[];
};
export type Recognition = {
  status: string;
  predicted_food: string | null;
  confidence: number | null;
  needs_review: boolean;
  model_version: string | null;
  top_predictions: { food_label: string; confidence: number }[];
  message: string | null;
  canonical_dish_id?: number | null;
  canonical_dish_name?: string | null;
  associated_recipes: AssociatedRecipe[];
};

export type FreshnessPrediction = {
  model_version: string;
  category: string;
  predicted_label: string;
  confidence: number;
  probabilities: Record<string, number>;
  device: string;
  safety_notice: string;
};
export type ToxiFruitPrediction = {
  predicted_class: string;
  category: "fruit" | "vegetable";
  fruit: "Apple" | "Banana" | "Malta" | "Mango" | null;
  vegetable: string | null;
  condition: "fresh_control" | "formalin_treated" | null;
  confidence: number;
  probabilities: Record<string, number>;
  model: string;
  model_version: string;
  interpretation: string;
};

export type CinnamonFTIRAnalysis = {
  sample_id: string | null;
  food: string;
  adulteration_status: "Pure_Cinnamon" | "Adulterated";
  is_adulterated: boolean;
  adulterant_type: "Peanut" | "Walnut" | "Wood_Dust" | null;
  estimated_concentration_percent: number;
  concentration_unit: "percent";
  model_version: string;
  validation_note: string;
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


export type RagClaim = {
  food_id: number;
  nutrient_key: string;
  amount: number;
  unit: string;
  basis_g: number;
};

export type RagEvidence = {
  source_type: string;
  source_id: string | number;
  title?: string | null;
  content?: string | null;
  provenance?: Record<string, unknown>;
  provenance_records?: Record<string, unknown>[];
  retrieval_sources?: string[];
  rank_score?: number;
  similarity_score?: number | null;
  source_conflicts?: unknown[];
  incomparable_measurements?: unknown[];
  invalid_measurements?: unknown[];
};

export type RagCitation = {
  citation_id: string;
  source_type: string;
  source_id: string | number;
  title?: string | null;
  provenance: Record<string, unknown>[];
};

export type RagResponse = {
  query: string;
  answer: string;
  retrieved_count: number;
  evidence: RagEvidence[];
  citations: RagCitation[];
  verification: {
    status: string;
    reason: string;
    supporting_evidence: Record<string, unknown>[];
    incomparable_evidence: Record<string, unknown>[];
  } | null;
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


// PHASE_3E_REGULATORY_API
export type RegulatoryProductType =
  | "bread" | "coffee_chicory" | "milk_product"
  | "edible_oil" | "sweetener_product" | "other";

export type RegulatoryTimeline = {
  assessment_date: string;
  amendment_count: number;
  product_compliance_assessed: boolean;
  compliance_verdict: null;
  notice: string;
  amendments: {
    amendment_id: string;
    effective_date: string | null;
    status: string;
    compliance_verdict: null;
  }[];
};

export type RegulatoryScreening = {
  product_type: RegulatoryProductType;
  assessment_date: string;
  candidate_count: number;
  screening_only: boolean;
  compliance_verdict: null;
  candidate_amendments: {
    amendment_id: string;
    date_status: string;
    affected_provisions: string[];
    compliance_verdict: null;
  }[];
};

export type RegulatoryBreadResult = {
  bread_type: string;
  data_sufficiency: string;
  minimum_whole_wheat_flour_percent_of_total_flour: number;
  supplied_whole_wheat_flour_percent_of_total_flour: number | null;
  compliance_verdict: null;
  legal_review_status: string;
};


// PHASE_3G_DOCUMENT_API

export type RegulatoryLabelField = {
  field: string;
  value: string;
  evidence_text: string;
  line_number: number;
  verification_status: "EXTRACTED_UNVERIFIED";
};

export type RegulatoryLabelExtraction = {
  extraction_method: string;
  source_text_truncated: boolean;
  fields: RegulatoryLabelField[];
  detected_field_count: number;
  not_detected: string[];
  facts_verified: false;
  compliance_verdict: null;
  notice: string;
};

export type RegulatoryDocumentPreview = {
  filename: string;
  content_type: string;
  size_bytes: number;
  document_kind: "pdf" | "image";
  extraction_status: string;
  extraction_engine: string | null;
  label_fields?: RegulatoryLabelExtraction;
  page_count: number | null;
  extracted_text: string;
  extracted_character_count: number;
  truncated: boolean;
  stored: false;
  regulatory_facts_verified: false;
  compliance_verdict: null;
  notice: string;
};


// PHASE_3H_DOCUMENT_EXTRACTION_API

// PHASE_3J_LABEL_SCREENING_API
export type RegulatoryLabelFinding = {
  field: string;
  status: string;
  severity: string;
  value: string | null;
  evidence_text: string | null;
  line_number: number | null;
  message: string;
};


// PHASE_3L3_CLAUSE_PREVIEW_TYPES
export type RegulatoryClauseEvidence = {
  field: string;
  value: string | null;
  evidence_text: string | null;
  line_number: number | null;
  verification_status: string;
};

export type RegulatoryClauseCandidate = {
  amendment_id: string;
  provision_reference: string;
  date_status: string | null;
  source_text_sha256: string | null;
  suggested_evidence_fields: string[];
  extracted_evidence: RegulatoryClauseEvidence[];
  field_mapping_status: string;
  product_applicability_verified: false;
  legal_review_status: string;
  requirement_text_verified: false;
  exceptions_checked: false;
  supersession_checked: false;
  rule_executed: false;
  compliance_verdict: null;
  finding_status: string;
};

export type RegulatoryClausePreview = {
  status?: string;
  provision_candidate_count: number;
  provision_candidates: RegulatoryClauseCandidate[];
  legal_review_complete: false;
  rule_execution_performed: false;
  compliance_verdict: null;
  notice: string;
};

export type RegulatoryLabelAssessment = {
  clause_preview?: RegulatoryClausePreview;
  product_type: RegulatoryProductType;
  assessment_date: string;
  document_type: string;
  document_type_verified: false;
  text_extraction_status: string;
  compliance_verdict: null;
  document_facts_verified: false;
  legal_review_status: string;
  detected_field_count: number;
  findings: RegulatoryLabelFinding[];
  candidate_amendment_count: number;
  potentially_relevant_amendments: {
    amendment_id: string;
    date_status: string;
    affected_provisions: string[];
    compliance_verdict: null;
  }[];
  source_document_warning: string | null;
  notice: string;
};

export function regulatoryLabelAssessment(
  file: File,
  productType: RegulatoryProductType,
  assessmentDate: string
) {
  const data = new FormData();
  data.append("file", file);
  data.append("product_type", productType);
  data.append("assessment_date", assessmentDate);
  return request<RegulatoryLabelAssessment>(
    "/regulatory/assessment/label-preview",
    { method: "POST", body: data }
  );
}

export function regulatoryDocumentExtract(file: File) {
  const payload = new FormData();
  payload.append("file", file);
  return request<RegulatoryDocumentPreview>(
    "/regulatory/documents/extract",
    { method: "POST", body: payload }
  );
}

export function regulatoryDocumentPreview(file: File) {
  const payload = new FormData();
  payload.append("file", file);
  return request<RegulatoryDocumentPreview>("/regulatory/documents/preview", {
    method: "POST",
    body: payload
  });
}

export function regulatoryAmendmentStatus(asOf: string) {
  return request<RegulatoryTimeline>(
    `/regulatory/amendments/status?as_of=${encodeURIComponent(asOf)}`
  );
}

export function regulatoryProductPreview(
  productType: RegulatoryProductType,
  assessmentDate: string
) {
  return request<RegulatoryScreening>("/regulatory/assessment/preview", {
    method: "POST",
    body: JSON.stringify({
      product_type: productType,
      assessment_date: assessmentDate
    })
  });
}

export function regulatoryBreadPreview(payload: {
  bread_type: "whole_wheat_bread" | "wheat_bread" | "brown_bread";
  assessment_date: string;
  whole_wheat_flour_percent: number | null;
}) {
  return request<RegulatoryBreadResult>(
    "/regulatory/assessment/bread-facts-preview",
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export const api = {
  generateRecipe: (payload: { title: string }) =>
    request<GeneratedRecipeResult>("/recipes/generate", { method: "POST", body: JSON.stringify(payload) }),


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

  recognize: (file: File, model: "food101" | "indian" = "food101") => {
    const data = new FormData();
    data.append("file", file);
    return request<Recognition>(`/recognition/predict?model=${model}`, {
      method: "POST",
      body: data,
    });
  },

  predictFreshness: (file: File, category: string) => {
    const data = new FormData();
    data.append("category", category);
    data.append("file", file);

    return request<FreshnessPrediction>("/freshness/predict", {
      method: "POST",
      body: data,
    });
  },
  screenProduce: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<ToxiFruitPrediction>("/food-fraud/produce/visual-screening", {
      method: "POST",
      body: data,
    });
  },

  analyzeCinnamonFTIR: (payload: {
    sample_id: string;
    spectral_values: number[];
  }) =>
    request<CinnamonFTIRAnalysis>("/food-fraud/cinnamon/ftir-analysis", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

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
  ragQuery: (payload: {
    query: string;
    top_k?: number;
    claim?: RagClaim;
  }) =>
    request<RagResponse>("/rag/query", {
      method: "POST",
      body: JSON.stringify(payload),
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


// PHASE_3L11_BREAD_DRAFT_API
export type RegulatoryBreadDraftRequest = {
  bread_type: string;
  ingredient_percent: string | null;
  measurement_basis: "100g_flour";
};

export type RegulatoryBreadDraftResponse = {
  bread_type: string;
  specialty_ingredient: string;
  draft_minimum_percent: number;
  measurement_basis: string;
  source_amendment_id: string;
  source_clause_id: string;
  source_pdf_page: number;
  source_pdf_sha256: string;
  supplied_percent: string | null;
  numerical_screening_status: string;
  product_facts_verified: false;
  legal_review_complete: false;
  rule_executed: false;
  compliance_verdict: null;
  notice: string;
};

export async function regulatoryBreadDraftPreview(
  payload: RegulatoryBreadDraftRequest
): Promise<RegulatoryBreadDraftResponse> {
  return request<RegulatoryBreadDraftResponse>(
    "/regulatory/assessment/bread-draft-preview",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}
