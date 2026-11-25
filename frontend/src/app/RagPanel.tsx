 "use client";

import { FormEvent, useState } from "react";
import { AlertTriangle, BookOpen, CheckCircle2, LoaderCircle, Search, ShieldCheck } from "lucide-react";
import { api, type RagClaim, type RagResponse } from "@/lib/api";

export default function RagPanel() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(8);
  const [includeClaim, setIncludeClaim] = useState(false);
  const [foodId, setFoodId] = useState("");
  const [nutrientKey, setNutrientKey] = useState("protein");
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState("g");
  const [basis, setBasis] = useState("100");
  const [result, setResult] = useState<RagResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query.trim().length < 2) return;

    let claim: RagClaim | undefined;

    if (includeClaim) {
      const parsedFoodId = Number(foodId);
      const parsedAmount = Number(amount);
      const parsedBasis = Number(basis);

      if (
        !Number.isInteger(parsedFoodId) || parsedFoodId <= 0 ||
        !nutrientKey.trim() || !Number.isFinite(parsedAmount) ||
        !unit.trim() || !Number.isFinite(parsedBasis) || parsedBasis <= 0
      ) {
        setError("Enter a valid food ID, nutrient, amount, unit and positive measurement basis.");
        return;
      }

      claim = {
        food_id: parsedFoodId,
        nutrient_key: nutrientKey.trim(),
        amount: parsedAmount,
        unit: unit.trim(),
        basis_g: parsedBasis,
      };
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await api.ragQuery({
        query: query.trim(),
        top_k: topK,
        ...(claim ? { claim } : {}),
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evidence retrieval failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rag-page">
      <div className="page-intro">
        <p className="eyebrow">GROUNDED FOOD KNOWLEDGE</p>
        <h1>Food <em>intelligence.</em></h1>
        <p>Search indexed food and nutrient evidence. Review source attribution, measurement limitations and conflicts before drawing conclusions.</p>
      </div>

      <form className="rag-search-panel" onSubmit={submit}>
        <label htmlFor="rag-query">What would you like to investigate?</label>
        <div className="rag-search-row">
          <Search size={19} aria-hidden="true" />
          <input
            id="rag-query"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="e.g. protein content of cooked rice"
            minLength={2}
            maxLength={500}
            required
          />
          <button className="button button-primary" type="submit" disabled={loading || query.trim().length < 2}>
            {loading ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />}
            {loading ? "Searching" : "Search evidence"}
          </button>
        </div>

        <div className="rag-search-options">
          <label>
            Evidence records
            <select value={topK} onChange={event => setTopK(Number(event.target.value))}>
              <option value={5}>5 records</option>
              <option value={8}>8 records</option>
              <option value={12}>12 records</option>
              <option value={20}>20 records</option>
            </select>
          </label>
          <label className="rag-claim-toggle">
            <input
              type="checkbox"
              checked={includeClaim}
              onChange={event => setIncludeClaim(event.target.checked)}
            />
            Verify a nutrient claim
          </label>
        </div>

        {includeClaim && (
          <div className="rag-claim-fields">
            <label>Food ID<input type="number" min="1" value={foodId} onChange={event => setFoodId(event.target.value)} required /></label>
            <label>Nutrient key<input value={nutrientKey} onChange={event => setNutrientKey(event.target.value)} required /></label>
            <label>Claimed amount<input type="number" step="any" value={amount} onChange={event => setAmount(event.target.value)} required /></label>
            <label>Unit<input value={unit} onChange={event => setUnit(event.target.value)} required /></label>
            <label>Basis (g)<input type="number" min="0.0001" step="any" value={basis} onChange={event => setBasis(event.target.value)} required /></label>
          </div>
        )}
      </form>

      {error && <div className="rag-error" role="alert"><AlertTriangle size={17} />{error}</div>}

      {loading && (
        <div className="rag-loading" role="status">
          <LoaderCircle className="spin" size={22} />
          <span>Searching indexed evidence and comparing sources...</span>
        </div>
      )}

      {!result && !loading && !error && (
        <div className="rag-empty">
          <span><BookOpen size={24} /></span>
          <h2>Evidence before conclusions.</h2>
          <p>Submit a question to retrieve indexed records with their provenance and measurement context.</p>
        </div>
      )}

      {result && (
        <div className="rag-results">
          <section className="rag-answer">
            <div className="rag-section-heading">
              <div><p className="eyebrow">RETRIEVAL SUMMARY</p><h2>What the evidence shows</h2></div>
              <span className="rag-count">{result.retrieved_count} records</span>
            </div>
            <p className="rag-answer-text">{result.answer}</p>
            <div className="rag-disclosure"><ShieldCheck size={16} /> Deterministic evidence summary | Not an AI-generated medical recommendation</div>
          </section>

          {result.verification && (
            <section className="rag-verification">
              <div className="rag-section-heading">
                <div><p className="eyebrow">CLAIM CHECK</p><h2>Nutrient verification</h2></div>
                {result.verification.status === "supported"
                  ? <CheckCircle2 size={21} />
                  : <AlertTriangle size={21} />}
              </div>
              <strong className={`rag-status rag-status-${result.verification.status}`}>
                {result.verification.status.replaceAll("_", " ")}
              </strong>
              <p>{result.verification.reason}</p>
              <small>Verification uses matching food ID, nutrient, unit and measurement basis. No unit conversion is assumed.</small>
            </section>
          )}

          <div className="rag-section-heading rag-evidence-heading">
            <div><p className="eyebrow">SOURCE RECORDS</p><h2>Retrieved evidence</h2></div>
            <span className="rag-count">{result.citations.length} citations</span>
          </div>

          {result.evidence.length === 0 ? (
            <div className="rag-empty rag-empty-small"><p>No matching indexed evidence was found for this query.</p></div>
          ) : (
            <div className="rag-evidence-list">
              {result.evidence.map((item, index) => {
                const citation = result.citations[index];
                const warningCount =
                  (item.source_conflicts?.length ?? 0) +
                  (item.incomparable_measurements?.length ?? 0) +
                  (item.invalid_measurements?.length ?? 0);

                return (
                  <article className="rag-evidence-card" key={`${item.source_type}:${item.source_id}`}>
                    <div className="rag-evidence-top">
                      <span className="rag-evidence-number">{String(index + 1).padStart(2, "0")}</span>
                      <span className="rag-source-type">{item.source_type.replaceAll("_", " ")}</span>
                      {warningCount > 0 && <span className="rag-warning"><AlertTriangle size={13} /> {warningCount} measurement warning(s)</span>}
                    </div>
                    <h3>{item.title || "Untitled evidence record"}</h3>
                    <p className="rag-evidence-content">{item.content || "No source text available."}</p>
                    <div className="rag-evidence-meta">
                      <span>Source ID: {String(item.source_id)}</span>
                      {item.retrieval_sources?.length ? <span>Retrieved by: {item.retrieval_sources.join(", ")}</span> : null}
                    </div>
                    {citation && (
                      <details className="rag-provenance">
                        <summary>View citation and provenance</summary>
                        <p className="rag-citation-id">{citation.citation_id}</p>
                        <pre>{JSON.stringify(citation.provenance, null, 2)}</pre>
                      </details>
                    )}
                    {warningCount > 0 && (
                      <details className="rag-provenance rag-warning-details">
                        <summary>Inspect measurement warnings</summary>
                        <pre>{JSON.stringify({
                          conflicts: item.source_conflicts,
                          incomparable: item.incomparable_measurements,
                          invalid: item.invalid_measurements,
                        }, null, 2)}</pre>
                      </details>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
