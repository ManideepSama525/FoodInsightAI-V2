"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileSpreadsheet,
  FlaskConical,
  LoaderCircle,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { api, type CinnamonFTIRAnalysis, type ToxiFruitPrediction } from "@/lib/api";

type Sample = {
  sampleId: string;
  adulterant: string;
  concentration: string;
  label: string;
  spectralValues: Float64Array;
};

const EXPECTED_FEATURE_COUNT = 2523;

const METADATA_COLUMNS = new Set([
  "sample_id",
  "adulterant",
  "concentration_pct",
  "sample_number",
  "food_fraud_class",
]);

function* csvRecords(text: string): Generator<string[]> {
  let row: string[] = [];
  let field = "";
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const character = text[i];

    if (quoted) {
      if (character === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += character;
      }
      continue;
    }

    if (character === '"' && field.length === 0) {
      quoted = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field);
      yield row;
      row = [];
      field = "";
    } else if (character !== "\r") {
      field += character;
    }
  }

  if (quoted) {
    throw new Error("The CSV contains an unclosed quoted field.");
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    yield row;
  }
}

function parseFTIRCSV(text: string): Sample[] {
  const records = csvRecords(text);
  const header = records.next();

  if (header.done || !header.value.length) {
    throw new Error("The CSV file is empty.");
  }

  const headers = header.value.map((value, index) =>
    index === 0 ? value.replace(/^\uFEFF/, "").trim() : value.trim()
  );

  const requiredMetadata = [
    "sample_id",
    "adulterant",
    "concentration_pct",
    "sample_number",
    "food_fraud_class",
  ];

  for (const name of requiredMetadata) {
    if (!headers.includes(name)) {
      throw new Error(`Required CSV column is missing: ${name}`);
    }
  }

  const featureIndices = headers
    .map((name, index) => ({ name, index }))
    .filter(({ name }) => !METADATA_COLUMNS.has(name))
    .map(({ index }) => index);

  if (featureIndices.length !== EXPECTED_FEATURE_COUNT) {
    throw new Error(
      `Expected ${EXPECTED_FEATURE_COUNT} FTIR spectral columns, found ${featureIndices.length}.`
    );
  }

  const indexOf = (name: string) => headers.indexOf(name);
  const samples: Sample[] = [];
  const sampleIds = new Set<string>();

  let rowNumber = 1;

  for (const record of records) {
    rowNumber += 1;

    if (record.length === 1 && record[0] === "") continue;

    if (record.length !== headers.length) {
      throw new Error(
        `CSV row ${rowNumber} has ${record.length} columns; expected ${headers.length}.`
      );
    }

    const sampleId = record[indexOf("sample_id")].trim();

    if (!sampleId) {
      throw new Error(`CSV row ${rowNumber} has no sample ID.`);
    }

    if (sampleIds.has(sampleId)) {
      throw new Error(`Duplicate sample ID found: ${sampleId}.`);
    }

    sampleIds.add(sampleId);

    const spectralValues = new Float64Array(EXPECTED_FEATURE_COUNT);

    for (let i = 0; i < featureIndices.length; i += 1) {
      const value = Number(record[featureIndices[i]]);

      if (!Number.isFinite(value)) {
        throw new Error(
          `Invalid spectral value at CSV row ${rowNumber}, feature ${i + 1}.`
        );
      }

      spectralValues[i] = value;
    }

    samples.push({
      sampleId,
      adulterant: record[indexOf("adulterant")],
      concentration: record[indexOf("concentration_pct")],
      label: record[indexOf("food_fraud_class")],
      spectralValues,
    });
  }

  if (samples.length === 0) {
    throw new Error("No valid sample records were found.");
  }

  return samples;
}

function displayAdulterant(value: string | null): string {
  if (value === "Wood_Dust") return "Wood dust";
  return value ?? "None detected";
}

export default function FoodFraudPanel() {
  const [fileName, setFileName] = useState("");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [selectedSampleId, setSelectedSampleId] = useState("");
  const [result, setResult] = useState<CinnamonFTIRAnalysis | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [produceFile, setProduceFile] = useState<File | null>(null);
  const [produceResult, setProduceResult] = useState<ToxiFruitPrediction | null>(null);
  const [produceBusy, setProduceBusy] = useState(false);
  const [produceError, setProduceError] = useState<string | null>(null);

  const selectedSample = useMemo(
    () => samples.find((sample) => sample.sampleId === selectedSampleId) ?? null,
    [samples, selectedSampleId]
  );

  async function handleFile(file: File | undefined) {
    if (!file) return;

    setError(null);
    setResult(null);
    setSamples([]);
    setSelectedSampleId("");
    setFileName("");

    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Upload a CSV file containing the trained FTIR spectral columns.");
      return;
    }

    if (file.size > 100 * 1024 * 1024) {
      setError("The CSV exceeds the 100 MB upload limit.");
      return;
    }

    setLoadingFile(true);

    try {
      const text = await file.text();
      const parsed = parseFTIRCSV(text);

      setSamples(parsed);
      setSelectedSampleId(parsed[0].sampleId);
      setFileName(file.name);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not read the FTIR CSV file."
      );
    } finally {
      setLoadingFile(false);
    }
  }

  async function analyseProduce() {
    if (!produceFile) return;

    setProduceBusy(true);
    setProduceResult(null);
    setProduceError(null);

    try {
      setProduceResult(await api.screenProduce(produceFile));
    } catch (cause) {
      setProduceError(
        cause instanceof Error ? cause.message : "Produce visual screening failed."
      );
    } finally {
      setProduceBusy(false);
    }
  }

  async function analyseSample() {
    if (!selectedSample) return;

    setAnalysing(true);
    setError(null);
    setResult(null);

    try {
      const response = await api.analyzeCinnamonFTIR({
        sample_id: selectedSample.sampleId,
        spectral_values: Array.from(selectedSample.spectralValues),
      });

      if (!response || !response.adulteration_status) {
        throw new Error("The analysis service returned an empty result.");
      }

      setResult(response);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "FTIR analysis failed. Check the API connection and try again."
      );
    } finally {
      setAnalysing(false);
    }
  }

  return (
    <>
      <div className="page-intro">
        <p className="eyebrow">FOOD AUTHENTICITY · FTIR ANALYSIS</p>
        <h1>Food fraud <em>detection.</em></h1>
        <p>
          Analyse cinnamon powder spectra using trained FTIR models to detect
          adulteration, identify the adulterant and estimate its concentration.
        </p>
      </div>

      <section className="upload-panel" style={{ marginBottom: "24px" }}>
        <div className="fraud-section-heading">
          <span className="fraud-icon"><ShieldCheck size={19} /></span>
          <div>
            <h2>Produce visual screening</h2>
            <p>Screen Apple, Banana, Malta, Mango and supported vegetables for visual patterns associated with the model dataset labels.</p>
          </div>
        </div>

        <label className="upload-zone fraud-upload">
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={produceBusy}
            onChange={(event) => {
              setProduceFile(event.target.files?.[0] ?? null);
              setProduceResult(null);
              setProduceError(null);
              event.currentTarget.value = "";
            }}
          />
          <span className="upload-symbol">
            {produceBusy
              ? <LoaderCircle className="spin" size={28} />
              : <Upload size={28} />}
          </span>
          <strong>{produceFile ? produceFile.name : "Upload produce image"}</strong>
          <small>JPG, PNG or WEBP · 4 fruits and 7 vegetable types</small>
        </label>

        {produceFile && (
          <div className="file-selected">
            <CheckCircle2 size={15} />
            <span>{produceFile.name}</span>
            <button
              type="button"
              onClick={() => {
                setProduceFile(null);
                setProduceResult(null);
                setProduceError(null);
              }}
            >
              Remove
            </button>
          </div>
        )}

        <button
          type="button"
          className="button button-primary full-button"
          disabled={!produceFile || produceBusy}
          onClick={analyseProduce}
        >
          {produceBusy
            ? <LoaderCircle className="spin" size={16} />
            : <ShieldCheck size={16} />}
          {produceBusy ? "Screening image..." : "Screen produce"}
        </button>

        {produceError && (
          <div className="fraud-error" role="alert">
            <AlertTriangle size={20} />
            <p>{produceError}</p>
          </div>
        )}

        {produceResult && (
          <section className="recipe-preview" aria-live="polite">
            <p className="eyebrow">PRODUCE SCREENING RESULT</p>
            <div className="confidence-row">
              <span>Predicted dataset label</span>
              <strong>{produceResult.predicted_class}</strong>
            </div>
            <div className="confidence-row">
              <span>Produce category</span>
              <strong>{produceResult.category === "fruit" ? "Fruit" : "Vegetable"}</strong>
            </div>
            {produceResult.category === "fruit" ? (
              <>
                <div className="confidence-row">
                  <span>Fruit</span>
                  <strong>{produceResult.fruit}</strong>
                </div>
                <div className="confidence-row">
                  <span>Dataset condition</span>
                  <strong>
                    {produceResult.condition === "fresh_control"
                      ? "Fresh control"
                      : "Formalin-treated label"}
                  </strong>
                </div>
              </>
            ) : (
              <div className="confidence-row">
                <span>Vegetable</span>
                <strong>{produceResult.vegetable}</strong>
              </div>
            )}
            <div className="confidence-row">
              <span>Model score</span>
              <strong>{(produceResult.confidence * 100).toFixed(1)}%</strong>
            </div>
            <h3>CLASS SCORES</h3>
            {Object.entries(produceResult.probabilities).map(([label, probability]) => (
              <div className="prediction-row" key={label}>
                <span>{label}</span>
                <strong>{(probability * 100).toFixed(1)}%</strong>
                <div className="confidence-track">
                  <i style={{ width: `${probability * 100}%` }} />
                </div>
              </div>
            ))}
            <p className="preview-note">{produceResult.interpretation}</p>
            <p className="preview-note">
              This is image-based screening, not chemical confirmation of formaldehyde.
              A Formalin-treated dataset label does not establish formaldehyde presence.
              A Fresh control label does not establish chemical safety.
            </p>
            <small>Model: {produceResult.model} · Version: {produceResult.model_version}</small>
          </section>
        )}
      </section>

      <div className="fraud-layout">
        <section className="upload-panel">
          <div className="fraud-section-heading">
            <span className="fraud-icon"><FileSpreadsheet size={19} /></span>
            <div>
              <h2>FTIR spectral dataset</h2>
              <p>Upload the processed cinnamon FTIR CSV dataset.</p>
            </div>
          </div>

          <label className="upload-zone fraud-upload">
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={loadingFile || analysing}
              onChange={(event) => {
                void handleFile(event.target.files?.[0]);
                event.currentTarget.value = "";
              }}
            />
            <span className="upload-symbol">
              {loadingFile
                ? <LoaderCircle className="spin" size={28} />
                : <Upload size={28} />}
            </span>
            <strong>
              {loadingFile ? "Reading spectral data..." : "Upload FTIR CSV"}
            </strong>
            <small>CSV · 2,523 spectral features per sample · Max 100 MB</small>
          </label>

          {fileName && (
            <div className="file-selected">
              <CheckCircle2 size={15} />
              <span>{fileName}</span>
            </div>
          )}

          {samples.length > 0 && (
            <>
              <div className="fraud-dataset-summary">
                <span>Samples loaded</span>
                <strong>{samples.length.toLocaleString()}</strong>
                <span>Spectral features per sample</span>
                <strong>{EXPECTED_FEATURE_COUNT.toLocaleString()}</strong>
              </div>

              <label className="fraud-field">
                Select sample for analysis
                <select
                  value={selectedSampleId}
                  disabled={analysing}
                  onChange={(event) => {
                    setSelectedSampleId(event.target.value);
                    setResult(null);
                    setError(null);
                  }}
                >
                  {samples.map((sample) => (
                    <option key={sample.sampleId} value={sample.sampleId}>
                      {sample.sampleId} · {sample.label} · {sample.concentration}%
                    </option>
                  ))}
                </select>
              </label>

              {selectedSample && (
                <div className="fraud-sample-details">
                  <span>Dataset sample information</span>
                  <p>Sample ID: <strong>{selectedSample.sampleId}</strong></p>
                  <p>Dataset class: <strong>{selectedSample.label}</strong></p>
                  <p>Dataset concentration: <strong>{selectedSample.concentration}%</strong></p>
                  <p>Adulterant metadata: <strong>{selectedSample.adulterant}</strong></p>
                </div>
              )}

              <button
                className="button button-primary full-button"
                disabled={!selectedSample || analysing || loadingFile}
                onClick={analyseSample}
              >
                {analysing
                  ? <LoaderCircle className="spin" size={16} />
                  : <FlaskConical size={16} />}
                {analysing ? "Analysing spectrum..." : "Analyse selected sample"}
              </button>
            </>
          )}

          <p className="privacy-note">
            Only the selected sample&apos;s spectral values are sent to the
            authenticated prediction API. The dataset class and concentration
            are displayed as source metadata, not used as model inputs.
          </p>
        </section>

        <section className="scan-result fraud-result" aria-live="polite">
          {error ? (
            <div className="fraud-error" role="alert">
              <AlertTriangle size={23} />
              <h2>Analysis could not be completed</h2>
              <p>{error}</p>
            </div>
          ) : result ? (
            <>
              <p className="eyebrow">MODEL ANALYSIS RESULT</p>
              <div className={`fraud-status ${result.is_adulterated ? "fraud-detected" : "fraud-pure"}`}>
                {result.is_adulterated
                  ? <AlertTriangle size={22} />
                  : <ShieldCheck size={22} />}
                <div>
                  <small>ADULTERATION STATUS</small>
                  <h2>
                    {result.is_adulterated ? "Adulteration detected" : "No adulteration detected"}
                  </h2>
                </div>
              </div>

              <div className="fraud-result-grid">
                <div>
                  <span>Food</span>
                  <strong>{result.food}</strong>
                </div>
                <div>
                  <span>Sample ID</span>
                  <strong>{result.sample_id ?? "Not provided"}</strong>
                </div>
                <div>
                  <span>Adulterant identified</span>
                  <strong>{displayAdulterant(result.adulterant_type)}</strong>
                </div>
                <div>
                  <span>Estimated concentration</span>
                  <strong>{result.estimated_concentration_percent.toFixed(3)}%</strong>
                </div>
              </div>

              <div className="fraud-model-info">
                <span>Model version</span>
                <strong>{result.model_version}</strong>
              </div>

              <div className="fraud-validation-note">
                <AlertTriangle size={17} />
                <div>
                  <strong>Research and validation limitations</strong>
                  <p>{result.validation_note}</p>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state tall">
              <FlaskConical />
              <h2>Your FTIR result will appear here.</h2>
              <p>
                Upload the processed CSV, select a sample and run the
                authenticated model inference.
              </p>
            </div>
          )}
        </section>
      </div>

    </>
  );
}

