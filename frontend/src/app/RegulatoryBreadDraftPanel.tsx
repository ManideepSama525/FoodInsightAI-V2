"use client";

import { useState, type FormEvent } from "react";
import {
  regulatoryBreadDraftPreview,
  type RegulatoryBreadDraftResponse,
} from "../lib/api";

const BREAD_TYPES = [
  ["whole_wheat_bread", "Whole wheat bread"],
  ["wheat_bread", "Wheat bread"],
  ["brown_bread", "Brown bread"],
  ["multigrain_bread", "Multigrain bread"],
  ["milk_bread", "Milk bread"],
  ["honey_bread", "Honey bread"],
  ["cheese_bread", "Cheese bread"],
  ["oatmeal_bread", "Oatmeal bread"],
  ["rye_bread", "Rye bread"],
  ["raisin_bread", "Raisin bread"],
  ["bran_bread", "Bran bread"],
] as const;

const shell: React.CSSProperties = {
  background: "#f8fbf7",
  border: "1px solid #dbe6da",
  borderRadius: 14,
  padding: 20,
  margin: "20px 0",
};

const field: React.CSSProperties = {
  width: "100%",
  padding: "11px 12px",
  border: "1px solid #c8d7c8",
  borderRadius: 8,
  background: "#fff",
  color: "#243c2b",
  fontSize: 14,
};

const caption: React.CSSProperties = {
  display: "block",
  fontWeight: 600,
  fontSize: 13,
  marginBottom: 7,
  color: "#365e42",
};

function explain(status: string): string {
  switch (status) {
    case "AT_OR_ABOVE_DRAFT_THRESHOLD":
      return "At or above the draft numerical threshold";
    case "BELOW_DRAFT_THRESHOLD":
      return "Below the draft numerical threshold";
    case "TRANSITIONAL_PERIOD_REVIEW_REQUIRED":
      return "Multigrain transition requires legal review";
    case "INSUFFICIENT_DATA":
      return "Insufficient or invalid formulation information";
    default:
      return "Result requires review";
  }
}

export default function RegulatoryBreadDraftPanel() {
  const [breadType, setBreadType] = useState("whole_wheat_bread");
  const [percentage, setPercentage] = useState("");
  const [result, setResult] =
    useState<RegulatoryBreadDraftResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function assess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError("");

    const clean = percentage.trim();
    if (clean && !/^(?:\d+(?:\.\d+)?|\.\d+)$/.test(clean)) {
      setError("Enter a percentage between 0 and 100.");
      return;
    }
    if (clean && (Number(clean) < 0 || Number(clean) > 100)) {
      setError("Percentage must be between 0 and 100.");
      return;
    }

    setLoading(true);
    try {
      const response = await regulatoryBreadDraftPreview({
        bread_type: breadType,
        ingredient_percent: clean || null,
        measurement_basis: "100g_flour",
      });
      if (
        response.compliance_verdict !== null ||
        response.rule_executed !== false ||
        response.legal_review_complete !== false ||
        response.product_facts_verified !== false
      ) {
        throw new Error("Unexpected regulatory verification status.");
      }
      setResult(response);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Bread screening request failed."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section style={shell} aria-label="Draft bread formulation screening">
      <h3 style={{ margin: "0 0 8px", color: "#274c35" }}>
        Bread formulation screening
      </h3>
      <p style={{ color: "#56675b", fontSize: 13, lineHeight: 1.6 }}>
        Compare a supplied specialty-ingredient percentage against
        historical FSSAI draft requirements. This tool does not verify
        your formulation, legal applicability or product compliance.
      </p>

      <form onSubmit={assess}>
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
          gap: 14,
          marginTop: 16,
        }}>
          <div>
            <label htmlFor="bread-draft-type" style={caption}>
              Bread category
            </label>
            <select
              id="bread-draft-type"
              style={field}
              value={breadType}
              onChange={(event) => {
                setBreadType(event.target.value);
                setResult(null);
                setError("");
              }}
            >
              {BREAD_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="bread-draft-percent" style={caption}>
              Specialty ingredient (% of total flour)
            </label>
            <input
              id="bread-draft-percent"
              style={field}
              type="number"
              min="0"
              max="100"
              step="any"
              value={percentage}
              placeholder="e.g. 75"
              onChange={(event) => {
                setPercentage(event.target.value);
                setResult(null);
                setError("");
              }}
            />
          </div>
        </div>

        <p style={{ color: "#647468", fontSize: 12 }}>
          Use formulation quantities, not an estimated percentage from
          an ingredient-list image. Leave blank if the value is unknown.
        </p>

        <button
          type="submit"
          disabled={loading}
          style={{
            background: "#326846",
            color: "#fff",
            border: 0,
            borderRadius: 9,
            padding: "11px 18px",
            fontWeight: 600,
            cursor: loading ? "wait" : "pointer",
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? "Checking draft values..." : "Compare draft threshold"}
        </button>
      </form>

      {error && (
        <p role="alert" style={{ color: "#a13732", marginTop: 14 }}>
          {error}
        </p>
      )}

      {result && (
        <div role="status" style={{
          background: "#fff",
          border: "1px solid #d7e2d5",
          borderRadius: 11,
          padding: 16,
          marginTop: 18,
        }}>
          <strong style={{ color: "#274c35" }}>
            {explain(result.numerical_screening_status)}
          </strong>
          <div style={{ marginTop: 12, fontSize: 14 }}>
            <p>
              <strong>Specialty ingredient:</strong>{" "}
              {result.specialty_ingredient}
            </p>
            <p>
              <strong>Draft minimum:</strong>{" "}
              {result.draft_minimum_percent}% of total flour
            </p>
            <p>
              <strong>Supplied value:</strong>{" "}
              {result.supplied_percent === null
                ? "Not provided or not accepted"
                : `${result.supplied_percent}%`}
            </p>
            <p>
              <strong>Source:</strong>{" "}
              {result.source_amendment_id},{" "}
              {result.source_clause_id}, PDF page{" "}
              {result.source_pdf_page}
            </p>
          </div>
          <p style={{
            color: "#91611c",
            background: "#fff6e5",
            padding: 12,
            borderRadius: 8,
            fontSize: 13,
            lineHeight: 1.6,
          }}>
            {result.notice}
          </p>
          <p style={{ fontSize: 12, color: "#667369" }}>
            Legal compliance verdict: Not issued.
            Source hash: {result.source_pdf_sha256}
          </p>
        </div>
      )}
    </section>
  );
}
