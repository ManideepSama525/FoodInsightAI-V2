"use client";
import RegulatoryBreadDraftPanel from "./RegulatoryBreadDraftPanel";

import { useEffect, useState, type CSSProperties } from "react";
import {
  AlertTriangle, CalendarDays, CheckCircle2, ClipboardList,
  FileSearch, LoaderCircle, Scale, ShieldAlert, Upload
} from "lucide-react";
import {
  regulatoryAmendmentStatus,
  regulatoryProductPreview,
  regulatoryBreadPreview,
  regulatoryDocumentExtract,

  regulatoryLabelAssessment,
  type RegulatoryLabelAssessment,

  type RegulatoryTimeline,
  type RegulatoryScreening,
  type RegulatoryBreadResult,
  type RegulatoryDocumentPreview,
  type RegulatoryProductType
} from "@/lib/api";

const categories: { value: RegulatoryProductType; label: string }[] = [
  { value: "bread", label: "Bread" },
  { value: "coffee_chicory", label: "Coffee and chicory" },
  { value: "milk_product", label: "Milk products" },
  { value: "edible_oil", label: "Edible oils" },
  { value: "sweetener_product", label: "Sweetener products" },
  { value: "other", label: "Other food" }
];

const breadTypes = [
  { value: "whole_wheat_bread", label: "Whole wheat bread" },
  { value: "wheat_bread", label: "Wheat bread" },
  { value: "brown_bread", label: "Brown bread" }
] as const;

const panel: CSSProperties = {
  background: "#fff",
  border: "1px solid #e5e9e2",
  borderRadius: 18,
  padding: 24,
  marginTop: 20
};

const field: CSSProperties = {
  display: "grid",
  gap: 8,
  color: "#344238",
  fontWeight: 600,
  fontSize: 14
};

const control: CSSProperties = {
  width: "100%",
  minHeight: 44,
  padding: "10px 12px",
  border: "1px solid #d8dfd6",
  borderRadius: 10,
  background: "#fff",
  color: "#1d3024",
  font: "inherit"
};

const secondary: CSSProperties = {
  color: "#69766c",
  fontSize: 14,
  lineHeight: 1.7
};

function dateStatus(value: string) {
  if (value === "FUTURE_REQUIREMENT") return "Future requirement";
  if (value === "EFFECTIVE_DATE_UNRESOLVED") return "Commencement unresolved";
  if (value === "PENDING_LEGAL_REVIEW") return "Legal review pending";
  return value.replaceAll("_", " ").toLowerCase();
}

export default function RegulatoryCompliancePanel() {
  const [productType, setProductType] = useState<RegulatoryProductType>("bread");
  const [date, setDate] = useState(() => {
    const now = new Date();
    const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  });
  const [timeline, setTimeline] = useState<RegulatoryTimeline | null>(null);
  const [screening, setScreening] = useState<RegulatoryScreening | null>(null);
  const [breadType, setBreadType] = useState<
    "whole_wheat_bread" | "wheat_bread" | "brown_bread"
  >("whole_wheat_bread");
  const [flourPercent, setFlourPercent] = useState("");
  const [breadResult, setBreadResult] = useState<RegulatoryBreadResult | null>(null);
  const [busy, setBusy] = useState(false);

  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [documentResult, setDocumentResult] =
    useState<RegulatoryDocumentPreview | null>(null);
  const [documentBusy, setDocumentBusy] = useState(false);

  const [labelAssessment, setLabelAssessment] =
    useState<RegulatoryLabelAssessment | null>(null);
  const [labelAssessmentBusy, setLabelAssessmentBusy] = useState(false);
  const [labelAssessmentError, setLabelAssessmentError] = useState("");

  async function runLabelScreening() {
    if (!documentFile) return;
    setLabelAssessmentBusy(true);
    setLabelAssessment(null);
    setLabelAssessmentError("");
    try {
      const result = await regulatoryLabelAssessment(
        documentFile, productType, date
      );
      setLabelAssessment(result);
    } catch (error) {
      setLabelAssessmentError(
        error instanceof Error
          ? error.message
          : "Label screening failed."
      );
    } finally {
      setLabelAssessmentBusy(false);
    }
  }

  const [documentError, setDocumentError] = useState("");

  async function uploadDocument() {
    if (!documentFile) return;
    if (documentFile.size > 8 * 1024 * 1024) {
      setDocumentError("The file exceeds the 8 MB limit.");
      return;
    }
    setDocumentBusy(true);
    setDocumentError("");
    setDocumentResult(null);
    try {
      setDocumentResult(await regulatoryDocumentExtract(documentFile));
    } catch (error) {
      setDocumentError(
        error instanceof Error ? error.message : "Document inspection failed."
      );
    } finally {
      setDocumentBusy(false);
    }
  }


  const [timelineBusy, setTimelineBusy] = useState(false);
  const [error, setError] = useState("");
  const [timelineError, setTimelineError] = useState("");

  useEffect(() => {
    let active = true;
    setTimelineBusy(true);
    setTimeline(null);
    setTimelineError("");
    regulatoryAmendmentStatus(date)
      .then(result => { if (active) setTimeline(result); })
      .catch(err => {
        if (active) setTimelineError(
          err instanceof Error ? err.message : "Could not load amendment timeline."
        );
      })
      .finally(() => { if (active) setTimelineBusy(false); });
    return () => { active = false; };
  }, [date]);

  async function assessProduct(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setScreening(null);
    setBreadResult(null);
    try {
      const response = await regulatoryProductPreview(productType, date);
      setScreening(response);
      if (productType === "bread") {
        const percentage = flourPercent.trim() === ""
          ? null
          : Number(flourPercent);
        if (
          percentage !== null &&
          (!Number.isFinite(percentage) || percentage < 0 || percentage > 100)
        ) {
          throw new Error("Whole-wheat flour percentage must be between 0 and 100.");
        }
        setBreadResult(await regulatoryBreadPreview({
          bread_type: breadType,
          assessment_date: date,
          whole_wheat_flour_percent: percentage
        }));
      }
    } catch (err) {
      setScreening(null);
      setBreadResult(null);
      setError(err instanceof Error ? err.message : "Regulatory screening failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-intro">
        <p className="eyebrow">FSSAI REGULATORY INTELLIGENCE</p>
        <h1>Regulatory <em>compliance.</em></h1>
        <p>
          Screen food products against documented Indian labelling amendments,
          review upcoming requirements, and identify information needing verification.
        </p>
      </div>

      <section style={{ ...panel, background: "#f4f8f2" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <ShieldAlert size={22} color="#4f765b" />
          <strong>Preliminary regulatory screening</strong>
        </div>
        <p style={{ ...secondary, marginTop: 8 }}>
          This workspace currently provides amendment discovery and limited
          product-fact screening. It does not issue legal compliance certification.
          Unverified requirements and subsequent directions require review.
        </p>
      </section>

      <section style={panel}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 16 }}>
          <ClipboardList size={22} color="#497857" />
          <h2 style={{ margin: 0 }}>Product information</h2>
        </div>
        <form onSubmit={assessProduct}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 18
          }}>
            <label style={field}>
              Product category
              <select
                style={control}
                value={productType}
                onChange={event => {
                  setProductType(event.target.value as RegulatoryProductType);
                  setScreening(null);
                  setLabelAssessment(null);
                  setBreadResult(null);
                }}
              >
                {categories.map(item =>
                  <option key={item.value} value={item.value}>{item.label}</option>
                )}
              </select>
            </label>
            <label style={field}>
              Assessment date
              <input
                style={control}
                required
                type="date"
                value={date}
                onChange={event => {
                  setDate(event.target.value);
                  setScreening(null);
                  setLabelAssessment(null);
                  setBreadResult(null);
                }}
              />
            </label>
          </div>

          {productType === "bread" && (
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: 18, marginTop: 18
            }}>
              <label style={field}>
                Bread label category
                <select
                  style={control}
                  value={breadType}
                  onChange={event => {
                    setBreadType(event.target.value as typeof breadType);
                    setBreadResult(null);
                  }}
                >
                  {breadTypes.map(item =>
                    <option key={item.value} value={item.value}>{item.label}</option>
                  )}
                </select>
              </label>
              <label style={field}>
                Whole-wheat flour (% of total flour)
                <input
                  style={control}
                  type="number"
                  min="0"
                  max="100"
                  step="any"
                  value={flourPercent}
                  onChange={event => {
                    setFlourPercent(event.target.value);
                    setBreadResult(null);
                  }}
                  placeholder="Optional; enter formulation data"
                />
              </label>
            </div>
          )}

          <p style={{ ...secondary, marginTop: 14 }}>
            Ingredient composition must come from reliable formulation records.
            A photograph alone cannot establish ingredient percentages.
          </p>
          <button
            className="button button-primary"
            type="submit"
            disabled={busy || !date}
            style={{ marginTop: 12 }}
          >
            {busy ? <LoaderCircle className="spin" size={16}/> : <FileSearch size={16}/>}
            {busy ? "Screening product..." : "Screen product"}
          </button>
        </form>
        {error && (
          <p role="alert" style={{ color: "#a43a38", marginTop: 16 }}>{error}</p>
        )}
      </section>


      <section style={panel}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Upload size={22} color="#497857"/>
          <h2 style={{ margin: 0 }}>Regulatory label document intake</h2>
        </div>
        <p style={secondary}>
          Upload a packaging image or PDF independently of Food Scan.
          PDFs with selectable text can be extracted where a PDF engine
          is available. English image OCR is available when installed. Extracted text is not a regulatory verdict.
        </p>
        <label style={field}>
          Product label or packaging document (maximum 8 MB)
          <input
            style={control}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp"
            onChange={event => {
              setDocumentFile(event.target.files?.[0] ?? null);
              setDocumentResult(null);
              setLabelAssessment(null);
              setDocumentError("");
            }}
          />
        </label>
        <button
          type="button"
          className="button button-primary"
          style={{ marginTop: 16 }}
          disabled={!documentFile || documentBusy}
          onClick={uploadDocument}
        >
          {documentBusy
            ? <LoaderCircle className="spin" size={16}/>
            : <FileSearch size={16}/>}
          {documentBusy ? "Inspecting document..." : "Inspect document"}
        </button>
        {documentError && (
          <p role="alert" style={{ color: "#a43a38", marginTop: 14 }}>
            {documentError}
          </p>
        )}
        {documentResult && (
          <div style={{
            background: "#f6f8f4",
            borderRadius: 12,
            padding: 18,
            marginTop: 18
          }}>
            <strong>Document inspection</strong>
            <p style={secondary}>
              {documentResult.filename} · {documentResult.size_bytes} bytes
            </p>
            <p>
              Extraction: <strong>
                {documentResult.extraction_status.replaceAll("_", " ")}
              </strong>
            </p>
            <p style={secondary}>{documentResult.notice}</p>


            <div style={{
              marginTop: 20,
              borderTop: "1px solid #e3e9df",
              paddingTop: 18
            }}>
              <button
                type="button"
                className="button button-secondary"
                onClick={runLabelScreening}
                disabled={!documentFile || labelAssessmentBusy}
              >
                {labelAssessmentBusy
                  ? "Screening label evidence..."
                  : "Screen label evidence"}
              </button>

              {labelAssessmentError && (
                <p role="alert" style={{ color: "#a43a38" }}>
                  {labelAssessmentError}
                </p>
              )}

              {labelAssessment && (
                <div style={{ marginTop: 18 }}>
                  <h3>Preliminary regulatory evidence review</h3>
                  <p style={secondary}>
                    Document classification:
                    {" "}{labelAssessment.document_type.replaceAll("_", " ")}
                  </p>

                  {labelAssessment.source_document_warning && (
                    <p role="alert" style={{ color: "#966021" }}>
                      {labelAssessment.source_document_warning}
                    </p>
                  )}

                  <p style={secondary}>
                    Candidate amendments:
                    {" "}{labelAssessment.candidate_amendment_count}.
                    Product applicability is not legally verified.
                  </p>


                  
                  {/* PHASE_3L3_CLAUSE_EVIDENCE */}
                  <section style={{
                    background: "#fff",
                    border: "1px solid #e3e9df",
                    borderRadius: 12,
                    padding: 18,
                    margin: "18px 0"
                  }}>
                    <h3 style={{ marginTop: 0 }}>
                      FSSAI provision evidence
                    </h3>
                    <p style={secondary}>
                      {labelAssessment.clause_preview
                        ? `${labelAssessment.clause_preview.provision_candidate_count} provision references found for preliminary review.`
                        : "Clause mapping has not been provided by this backend response."}
                    </p>

                    {labelAssessment.clause_preview?.status ===
                      "UNAVAILABLE_NEEDS_REVIEW" && (
                      <p role="alert" style={{ color: "#966021" }}>
                        Clause mapping unavailable. Existing label screening
                        results remain preliminary.
                      </p>
                    )}

                    {labelAssessment.clause_preview &&
                      labelAssessment.clause_preview.provision_candidates.length > 0 && (
                      <details>
                        <summary style={{
                          cursor: "pointer",
                          color: "#365e42",
                          fontWeight: 600
                        }}>
                          View provision references and supporting evidence
                        </summary>

                        <div style={{ marginTop: 12 }}>
                          {labelAssessment.clause_preview.provision_candidates.map(
                            (candidate, index) => (
                              <div
                                key={`${candidate.amendment_id}-${candidate.provision_reference}-${index}`}
                                style={{
                                  borderTop: "1px solid #e3e9df",
                                  padding: "14px 0",
                                  overflowWrap: "anywhere"
                                }}
                              >
                                <strong>{candidate.provision_reference}</strong>
                                <p style={secondary}>
                                  Amendment: {candidate.amendment_id}
                                </p>
                                <p style={secondary}>
                                  Date status: {candidate.date_status ??
                                    "Unresolved"}
                                </p>
                                <p style={{ color: "#966021", fontSize: 13 }}>
                                  Needs legal review. Product applicability,
                                  exemptions and supersession are unverified.
                                </p>

                                {candidate.extracted_evidence.length > 0 ? (
                                  candidate.extracted_evidence.map(
                                    (evidence, evidenceIndex) => (
                                      <div key={evidenceIndex} style={{
                                        background: "#f7faf5",
                                        borderRadius: 8,
                                        padding: 12,
                                        marginTop: 8
                                      }}>
                                        <strong>
                                          {evidence.field.replaceAll("_", " ")}
                                        </strong>
                                        <p style={{ ...secondary, margin: "5px 0" }}>
                                          {evidence.value ?? "No value"}
                                        </p>
                                        <p style={secondary}>
                                          Source line {evidence.line_number ??
                                            "unknown"}: {evidence.evidence_text ??
                                            "Source text unavailable"}
                                        </p>
                                      </div>
                                    )
                                  )
                                ) : (
                                  <p style={secondary}>
                                    No matching label evidence was mapped.
                                    This is not proof of a missing legal declaration.
                                  </p>
                                )}

                                <p style={{ ...secondary, fontSize: 11 }}>
                                  Source-text SHA-256:
                                  {" "}{candidate.source_text_sha256 ??
                                    "Unavailable"}
                                </p>
                              </div>
                            )
                          )}
                        </div>
                      </details>
                    )}

                    {labelAssessment.clause_preview && (
                      <p style={{ ...secondary, marginBottom: 0 }}>
                        {labelAssessment.clause_preview.notice}
                      </p>
                    )}
                  </section>


                  {/* PHASE_3L11_BREAD_PANEL */}
                  <RegulatoryBreadDraftPanel />

                  {/* PHASE_3K_COMPACT_REVIEW */}
                  <div style={{
                    display: "grid",
                    gridTemplateColumns:
                      "repeat(auto-fit, minmax(155px, 1fr))",
                    gap: 12,
                    margin: "20px 0"
                  }}>
                    {[
                      {
                        label: "Fields detected",
                        count: labelAssessment.findings.filter(
                          item => item.status !== "NOT_DETECTED"
                        ).length
                      },
                      {
                        label: "Needs attention",
                        count: labelAssessment.findings.filter(
                          item => item.status ===
                            "SUSPECTED_TEST_OR_PLACEHOLDER_VALUE" ||
                            item.status ===
                            "REQUIRES_MANUAL_VERIFICATION"
                        ).length
                      },
                      {
                        label: "Not detected",
                        count: labelAssessment.findings.filter(
                          item => item.status === "NOT_DETECTED"
                        ).length
                      }
                    ].map(metric => (
                      <div key={metric.label} style={{
                        padding: 16,
                        border: "1px solid #e2e9df",
                        borderRadius: 12,
                        background: "#f7faf5"
                      }}>
                        <div style={{
                          fontSize: 27,
                          fontWeight: 700,
                          color: "#365e42"
                        }}>
                          {metric.count}
                        </div>
                        <div style={{
                          ...secondary,
                          fontSize: 12,
                          fontWeight: 600
                        }}>
                          {metric.label}
                        </div>
                      </div>
                    ))}
                  </div>

                  {labelAssessment.findings
                    .filter(item =>
                      item.status ===
                        "SUSPECTED_TEST_OR_PLACEHOLDER_VALUE" ||
                      item.status ===
                        "REQUIRES_MANUAL_VERIFICATION"
                    )
                    .map(item => (
                      <div key={item.field} style={{
                        padding: 16,
                        marginBottom: 12,
                        background: "#fff8ec",
                        border: "1px solid #ead8b5",
                        borderRadius: 12
                      }}>
                        <strong>
                          Review required: {item.field.replaceAll("_", " ")}
                        </strong>
                        <p style={{
                          ...secondary,
                          marginBottom: 0
                        }}>
                          {item.message}
                        </p>
                      </div>
                    ))}

                  <details style={{
                    border: "1px solid #e3e9df",
                    borderRadius: 12,
                    padding: 16,
                    marginTop: 16
                  }}>
                    <summary style={{
                      cursor: "pointer",
                      color: "#365e42",
                      fontWeight: 600
                    }}>
                      View all {labelAssessment.findings.length}
                      {" "}evidence findings and source references
                    </summary>
                    <div style={{ marginTop: 14 }}>
                  {labelAssessment.findings.map(item => (
                    <div
                      key={item.field}
                      style={{
                        borderTop: "1px solid #e3e9df",
                        padding: "13px 0",
                        overflowWrap: "anywhere"
                      }}
                    >
                      <strong>{item.field.replaceAll("_", " ")}</strong>
                      <p style={{
                        ...secondary,
                        margin: "5px 0"
                      }}>
                        Status: {item.status.replaceAll("_", " ")}
                      </p>
                      {item.value && <p>{item.value}</p>}
                      <p style={secondary}>{item.message}</p>
                      {item.evidence_text && (
                        <p style={secondary}>
                          Source line {item.line_number}:
                          {" "}{item.evidence_text}
                        </p>
                      )}
                    </div>
                  ))}


                    </div>
                  </details>

                  <p style={{
                    ...secondary,
                    fontWeight: 600,
                    marginTop: 16
                  }}>
                    {labelAssessment.notice}
                  </p>
                </div>
              )}
            </div>

            {documentResult.label_fields && !labelAssessment && (
              <div style={{ marginTop: 20 }}>
                <h3>Detected label declarations</h3>
                <p style={secondary}>
                  {documentResult.label_fields.detected_field_count}
                  {" "}text-based candidate fields detected.
                  None have been independently verified.
                </p>
                {documentResult.label_fields.fields.map(item => (
                  <div key={item.field} style={{
                    borderTop: "1px solid #e3e9df",
                    padding: "12px 0",
                    overflowWrap: "anywhere"
                  }}>
                    <strong>
                      {item.field.replaceAll("_", " ")}
                    </strong>
                    <p style={{ margin: "7px 0" }}>{item.value}</p>
                    <p style={secondary}>
                      Source line {item.line_number}:
                      {" "}{item.evidence_text}
                    </p>
                    <span style={{
                      color: "#946820",
                      fontSize: 12,
                      fontWeight: 600
                    }}>
                      EXTRACTED — NOT VERIFIED
                    </span>
                  </div>
                ))}
                <p style={{ ...secondary, marginTop: 16 }}>
                  Not detected in extracted text:
                  {" "}{documentResult.label_fields.not_detected.length
                    ? documentResult.label_fields.not_detected
                        .map(item => item.replaceAll("_", " ")).join(", ")
                    : "None"}
                </p>
                <p style={secondary}>
                  {documentResult.label_fields.notice}
                </p>
              </div>
            )}

            {documentResult.extracted_text && (
              <div>
                <h3>Extracted {documentResult.document_kind === "pdf" ? "PDF" : "image"} text (unverified)</h3>
                <textarea
                  aria-label="Extracted document text"
                  readOnly
                  value={documentResult.extracted_text}
                  rows={9}
                  style={{
                    ...control,
                    minHeight: 180,
                    fontFamily: "inherit"
                  }}
                />
                <p style={secondary}>
                  {documentResult.truncated
                    ? "Preview truncated; not all source text is shown."
                    : "Text is not automatically verified or assessed."}
                </p>
              </div>
            )}
          </div>
        )}
      </section>

      {screening && (
        <section style={panel} aria-label="Screening results">
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <AlertTriangle color="#af7b22" size={21}/>
            <h2 style={{ margin: 0 }}>Regulatory screening findings</h2>
          </div>
          <p style={secondary}>
            {screening.candidate_count} potentially relevant amendment
            {screening.candidate_count === 1 ? "" : "s"} found.
            This list is not a complete legal-applicability determination.
          </p>
          {screening.candidate_amendments.map(item => (
            <div key={item.amendment_id} style={{
              borderTop: "1px solid #edf0eb", padding: "14px 0"
            }}>
              <strong>{item.amendment_id}</strong>
              <div style={secondary}>{dateStatus(item.date_status)}</div>
              <div style={secondary}>
                Provisions: {item.affected_provisions.join(", ")}
              </div>
              <div style={secondary}>Legal review pending</div>
            </div>
          ))}
          {screening.candidate_count === 0 && (
            <p style={secondary}>
              No category-specific amendments matched this preview.
              This does not mean that the product has no regulatory obligations.
            </p>
          )}
          {breadResult && (
            <div style={{ borderTop: "1px solid #edf0eb", paddingTop: 16 }}>
              <h3>Bread formulation reference</h3>
              <p>
                Documented candidate minimum: <strong>
                  {breadResult.minimum_whole_wheat_flour_percent_of_total_flour}%
                </strong> of total flour.
              </p>
              <p style={secondary}>
                Supplied: {breadResult.supplied_whole_wheat_flour_percent_of_total_flour ?? "Not provided"}%
                {" · "}Data: {breadResult.data_sufficiency.replaceAll("_", " ")}
              </p>
              <p style={secondary}>
                Schedule-II paragraph 2.6 · Legal review still required.
                No final threshold or compliance verdict is issued.
              </p>
            </div>
          )}
        </section>
      )}

      <section style={panel}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <CalendarDays color="#497857" size={22}/>
          <h2 style={{ margin: 0 }}>FSSAI amendment timeline</h2>
        </div>
        <p style={secondary}>
          Labelling and Display amendments for the selected assessment date.
        </p>
        {timelineBusy && <p style={secondary}><LoaderCircle className="spin" size={16}/> Loading timeline...</p>}
        {timelineError && <p role="alert" style={{ color: "#a43a38" }}>{timelineError}</p>}
        {timeline && (
          <div>
            {timeline.amendments.map(item => (
              <div key={item.amendment_id} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 16,
                flexWrap: "wrap",
                padding: "14px 0",
                borderBottom: "1px solid #edf0eb"
              }}>
                <div>
                  <strong>{item.amendment_id}</strong>
                  <div style={secondary}>
                    Effective date: {item.effective_date ?? "Pending verification"}
                  </div>
                </div>
                <span style={{
                  borderRadius: 100,
                  padding: "6px 12px",
                  background: "#f0f3ed",
                  color: "#405a48",
                  fontSize: 12,
                  fontWeight: 600
                }}>
                  {dateStatus(item.status)}
                </span>
              </div>
            ))}
            <p style={{ ...secondary, marginTop: 15 }}>{timeline.notice}</p>
          </div>
        )}
      </section>

      <section style={{ ...panel, marginBottom: 28 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Scale color="#497857" size={22}/>
          <h2 style={{ margin: 0 }}>Assessment limitations</h2>
        </div>
        <p style={secondary}>
          Current results are limited to the curated FSSAI labelling amendment
          inventory. Product-specific exemptions, regulatory directions, complete
          packaging evidence and other legal requirements have not all been
          reconciled. A missing finding is not evidence of compliance.
        </p>
        <p style={{ ...secondary, display: "flex", alignItems: "center", gap: 8 }}>
          <CheckCircle2 color="#497857" size={17}/>
          Food Scan, Food Fraud and Nutrition remain independent modules.
        </p>
      </section>
    </div>
  );
}
