from pathlib import Path
from datetime import datetime
import json
import shutil
import subprocess
import sys

ROOT = Path.cwd()
PAGE = ROOT / "frontend/src/app/page.tsx"
API = ROOT / "frontend/src/lib/api.ts"
PANEL = ROOT / "frontend/src/app/RegulatoryCompliancePanel.tsx"
REPORT = ROOT / "logs/regulatory_phase3e_implementation_report.txt"
BACKUP = ROOT / "backups" / (
    "regulatory_frontend_phase3e_" +
    datetime.now().strftime("%Y%m%d_%H%M%S_%f")
)

notes = ["FOODINSIGHTAI PHASE 3E - STANDALONE FRONTEND"]
changed = False

def record(message):
    notes.append(str(message))

def fail(message):
    record("STATUS: FAILED")
    record("ERROR: " + str(message))
    REPORT.write_text("\n".join(notes), encoding="utf-8")
    print("FAILED:", message)
    print("REPORT:", REPORT)
    sys.exit(1)

def replace_once(content, old, new, label):
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            label + ": expected one anchor, found " + str(count)
        )
    return content.replace(old, new, 1)

if not PAGE.is_file() or not API.is_file():
    fail("Missing frontend page or API client")

if PANEL.exists():
    fail("RegulatoryCompliancePanel.tsx already exists")

page_original = PAGE.read_text(encoding="utf-8-sig")
api_original = API.read_text(encoding="utf-8-sig")

if 'id:"regulatory"' in page_original:
    fail("Regulatory navigation already present")

if "PHASE_3E_REGULATORY_API" in api_original:
    fail("Regulatory API client already installed")

panel_source = r'''"use client";

import { useEffect, useState, type CSSProperties } from "react";
import {
  AlertTriangle, CalendarDays, CheckCircle2, ClipboardList,
  FileSearch, LoaderCircle, Scale, ShieldAlert
} from "lucide-react";
import {
  regulatoryAmendmentStatus,
  regulatoryProductPreview,
  regulatoryBreadPreview,
  type RegulatoryTimeline,
  type RegulatoryScreening,
  type RegulatoryBreadResult,
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
'''

api_addition = r'''
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

'''

try:
    page_updated = replace_once(
        page_original,
        'import FoodFraudPanel from "./FoodFraudPanel";',
        'import FoodFraudPanel from "./FoodFraudPanel";\n'
        'import RegulatoryCompliancePanel from "./RegulatoryCompliancePanel";',
        "Panel import",
    )

    page_updated = replace_once(
        page_updated,
        'Search, ShieldCheck, Sparkles',
        'Search, ShieldCheck, Scale, Sparkles',
        "Scale icon import",
    )

    page_updated = replace_once(
        page_updated,
        '| "rag" | "fraud";',
        '| "rag" | "fraud" | "regulatory";',
        "Tab type",
    )

    page_updated = replace_once(
        page_updated,
        '{id:"fraud",label:"Food fraud",icon:ShieldCheck},{id:"profile"',
        '{id:"fraud",label:"Food fraud",icon:ShieldCheck},'
        '{id:"regulatory",label:"Regulatory compliance",icon:Scale},{id:"profile"',
        "Sidebar navigation",
    )

    page_updated = replace_once(
        page_updated,
        '{tab==="fraud"&&<FoodFraudPanel />}',
        '{tab==="fraud"&&<FoodFraudPanel />}\n'
        '        {tab==="regulatory"&&<RegulatoryCompliancePanel />}',
        "Standalone panel routing",
    )

    if "async function request<T>" not in api_original:
        raise RuntimeError("Authenticated API request helper missing")

    api_updated = replace_once(
        api_original,
        "export const api = {",
        api_addition + "export const api = {",
        "Authenticated regulatory API integration",
    )

except Exception as exc:
    fail(exc)

BACKUP.mkdir(parents=True, exist_ok=False)

shutil.copy2(PAGE, BACKUP / "page.tsx")
shutil.copy2(API, BACKUP / "api.ts")

record("BACKUP: " + str(BACKUP))

try:
    PAGE.write_text(page_updated, encoding="utf-8")
    API.write_text(api_updated, encoding="utf-8")
    PANEL.write_text(panel_source, encoding="utf-8")
    changed = True

    checks = {
        "sidebar": 'label:"Regulatory compliance"' in PAGE.read_text(encoding="utf-8"),
        "standalone_panel": 'tab==="regulatory"&&<RegulatoryCompliancePanel />' in PAGE.read_text(encoding="utf-8"),
        "authenticated_api": 'PHASE_3E_REGULATORY_API' in API.read_text(encoding="utf-8"),
        "food_scan_tab_preserved": 'id:"recognition",label:"Food scan"' in PAGE.read_text(encoding="utf-8"),
        "food_fraud_tab_preserved": 'id:"fraud",label:"Food fraud"' in PAGE.read_text(encoding="utf-8"),
    }

    for name, result in checks.items():
        record("CHECK_" + name.upper() + ": " + ("PASS" if result else "FAIL"))
    if not all(checks.values()):
        raise RuntimeError("Structural verification failed")

    frontend = ROOT / "frontend"
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found in PATH")

    for script in ("typecheck", "build"):
        record("RUNNING: npm run " + script)
        result = subprocess.run(
            [npm, "run", script],
            cwd=frontend,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
        )
        record(script.upper() + "_EXIT_CODE: " + str(result.returncode))
        record(script.upper() + "_OUTPUT:")
        record((result.stdout + "\n" + result.stderr)[-12000:])
        if result.returncode:
            raise RuntimeError("Frontend " + script + " failed")

    record("STATUS: PASSED")
    record("STANDALONE_REGULATORY_PAGE: INSTALLED")
    record("FOOD_SCAN_MODIFIED: NO")
    record("BACKEND_MODIFIED: NO")
    record("DATABASE_MODIFIED: NO")
    record("COMPLIANCE_VERDICTS: DISABLED")

except Exception as exc:
    if changed:
        shutil.copy2(BACKUP / "page.tsx", PAGE)
        shutil.copy2(BACKUP / "api.ts", API)
        if PANEL.exists():
            PANEL.unlink()
    record("STATUS: FAILED_AND_ROLLED_BACK")
    record("ERROR: " + str(exc))
    record("FRONTEND_SOURCE_RESTORED: YES")
    REPORT.write_text("\n".join(notes), encoding="utf-8")
    print("PHASE 3E FAILED. REPORT:", REPORT)
    sys.exit(1)

REPORT.write_text("\n".join(notes), encoding="utf-8")
print("PHASE 3E PASSED")
print("REPORT:", REPORT)
print("BACKUP:", BACKUP)
