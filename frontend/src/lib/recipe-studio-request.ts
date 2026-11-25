/** Recipe Studio transport: preserve existing api.ts, but retain structured 409 assessment. */
import { session, type FoodSafetyResult, type GeneratedRecipeResult } from "@/lib/api";

export type RecipeStudioResult = GeneratedRecipeResult & {
  safety?: FoodSafetyResult | null;
  quality_warnings?: string[];
};

export class RecipeStudioConflict extends Error {
  readonly assessment: FoodSafetyResult | null;
  readonly code: string;

  constructor(message: string, code: string, assessment: FoodSafetyResult | null) {
    super(message);
    this.name = "RecipeStudioConflict";
    this.code = code;
    this.assessment = assessment;
  }
}

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

export async function generateRecipeForStudio(title: string): Promise<RecipeStudioResult> {
  const token = session.getToken();
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${base}/recipes/generate`, {
    method: "POST",
    headers,
    cache: "no-store",
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = object(object(body)?.detail);
    if (response.status === 409 && detail &&
        (detail.code === "RECIPE_REQUEST_CONFLICT" || detail.code === "GENERATED_RECIPE_CONFLICT")) {
      const rawAssessment = object(detail.assessment);
      const assessment = rawAssessment && Array.isArray(rawAssessment.matches) &&
        typeof rawAssessment.disclaimer === "string"
        ? rawAssessment as FoodSafetyResult : null;
      throw new RecipeStudioConflict(
        typeof detail.message === "string" ? detail.message : "This recipe conflicts with your Food Profile.",
        String(detail.code),
        assessment,
      );
    }
    if (response.status === 401) {
      session.clear();
      if (typeof window !== "undefined") window.dispatchEvent(new Event("foodinsightai:unauthorized"));
    }
    const msg = object(body)?.detail;
    throw new Error(typeof msg === "string" ? msg : `Recipe generation failed (${response.status}).`);
  }
  return response.json() as Promise<RecipeStudioResult>;
}
