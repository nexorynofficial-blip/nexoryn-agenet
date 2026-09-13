"use client";

/**
 * Floating AI assistant button for the Nexoryn Dashboard's New
 * Project page. Renders a small circular button in the bottom-right
 * corner; clicking it opens a panel where the admin pastes a project
 * summary and picks images.
 *
 * On submit, it:
 *   1. Calls this project's Python backend (POST /extract) to turn
 *      the summary into structured data matching the real project
 *      schema (see PORTFOLIO_FORM_REFERENCE.md).
 *   2. Uploads each selected image directly to the dashboard's own
 *      POST /api/v1/admin/assets, using the admin's existing session
 *      cookie (credentials: "include") — no separate credentials
 *      needed, since this runs inside the already-authenticated tab.
 *   3. Calls `onAutofill` with everything assembled, so the PARENT
 *      page (ProjectForm.tsx) can apply it to its own real form
 *      state — the admin then sees the actual fields filled in and
 *      reviews them in place.
 *
 * This component NEVER calls POST/PUT /api/v1/admin/projects and
 * has no code path that could — filling the form and saving it are
 * deliberately kept as separate, structurally disconnected steps.
 * The admin always clicks "Save Project" themselves.
 *
 * Visual design matches the site's dark "forge" theme (near-black +
 * glassmorphism + warm orange-to-gold gradient + film grain) — see
 * the injected <style> below for the full token set.
 */
import { useEffect, useRef, useState } from "react";

export interface UploadedAsset {
  id: string;
  url: string;
  altText: string;
  width?: number;
  height?: number;
}

export interface AutofillPayload {
  service: "Automation" | "Web Development" | "Brand & Graphic Design";
  title: string;
  industry: string;
  description: string;
  tags: string[];
  /** Shaped like caseStudy in PORTFOLIO_FORM_REFERENCE.md §4.2, minus gallery/photoId. */
  caseStudy: Record<string, unknown>;
  /** In the order the admin selected them. The first is a reasonable default thumbnail. */
  uploadedAssets: UploadedAsset[];
}

interface ReviewReport {
  ok: string[];
  warnings: string[];
  blocking: string[];
}

interface ExtractResponse {
  service: AutofillPayload["service"];
  payload: {
    title: string;
    industry: string;
    description: string;
    tags: string[];
    caseStudy: Record<string, unknown>;
  };
  review: ReviewReport;
}

interface FloatingAgentWidgetProps {
  /** Base URL of this project's Python agent backend, e.g. http://localhost:8000 */
  backendApiBaseUrl: string;
  /** Base URL of the Nexoryn dashboard's own API. Leave empty/omit when the
   * widget is bundled into the same app (the common case) — relative URLs
   * already hit the right origin. */
  dashboardApiBaseUrl?: string;
  /** Called with everything assembled once extraction + uploads finish.
   * Wire this up in ProjectForm.tsx to apply the data to its own state. */
  onAutofill: (payload: AutofillPayload) => void;
}

type Stage = "form" | "loading" | "done" | "error";

const GRAIN_SVG = `data:image/svg+xml,${encodeURIComponent(
  `<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>`
)}`;

const STYLE_SHEET = `
.nxai-root {
  --night: #150c05;
  --amber-deep: #3a1c05;
  --glow: #c85a12;
  --accent-from: #ff7a1a;
  --accent-to: #ffb300;
  --body-light: #e5e5e5;
  --body-dim: #cfcfcf;
  --status-green: #22c55e;
  --status-red: #f87171;
  --glass-border: rgba(255,255,255,0.15);
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-out-strong: cubic-bezier(0.19, 1, 0.22, 1);
  --ease-in-out-strong: cubic-bezier(0.87, 0, 0.13, 1);
  --ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
  font-family: 'Manrope', system-ui, sans-serif;
}
.nxai-fab {
  position: fixed; bottom: 24px; right: 24px; width: 60px; height: 60px;
  border-radius: 50%; border: 1px solid var(--glass-border); background: var(--night);
  cursor: pointer; padding: 0; overflow: hidden; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  transition: transform 0.35s var(--ease-out-expo);
  animation: nxai-breathe 2.8s var(--ease-in-out-strong) infinite;
}
.nxai-fab:hover { transform: scale(1.06); }
.nxai-fab:active { transform: scale(0.94); }
.nxai-fab-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.nxai-fab-glyph { font-size: 20px; color: var(--body-light); line-height: 1; }
.nxai-status-dot {
  position: absolute; top: 3px; right: 3px; width: 10px; height: 10px; border-radius: 50%;
  background: var(--status-green); border: 2px solid var(--night); z-index: 2;
  animation: nxai-pulse 2s var(--ease-out-strong) infinite;
}
.nxai-status-dot.offline { background: #6b7280; animation: none; }
@keyframes nxai-breathe {
  0%, 100% { box-shadow: 0 0 0 1px var(--glass-border), 0 0 16px 2px rgba(200,90,18,0.3), 0 6px 20px rgba(0,0,0,0.6); }
  50% { box-shadow: 0 0 0 1px var(--glass-border), 0 0 30px 8px rgba(255,122,26,0.55), 0 6px 20px rgba(0,0,0,0.6); }
}
@keyframes nxai-pulse {
  0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.6); }
  70% { box-shadow: 0 0 0 8px rgba(34,197,94,0); }
  100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}
.nxai-panel {
  position: fixed; bottom: 96px; right: 24px; width: 380px; max-height: 74vh;
  border-radius: 18px; border: 1px solid var(--glass-border);
  background: rgba(0,0,0,0.58);
  backdrop-filter: blur(28px) saturate(150%);
  -webkit-backdrop-filter: blur(28px) saturate(150%);
  box-shadow: 0 20px 60px rgba(0,0,0,0.65);
  display: flex; flex-direction: column; overflow: hidden; z-index: 1000;
  animation: nxai-panel-in 0.4s var(--ease-drawer);
}
@keyframes nxai-panel-in {
  from { opacity: 0; transform: translateY(14px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.nxai-grain {
  position: absolute; inset: 0; pointer-events: none; opacity: 0.05;
  mix-blend-mode: overlay; background-image: url("${GRAIN_SVG}");
}
.nxai-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px; border-bottom: 1px solid var(--glass-border);
  position: relative; z-index: 1;
}
.nxai-title {
  font-family: 'Montserrat', sans-serif; font-weight: 800; text-transform: uppercase;
  letter-spacing: 0.04em; font-size: 12.5px; color: var(--body-light);
  display: flex; align-items: center; gap: 8px;
}
.nxai-title-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--status-green); animation: nxai-pulse 2s var(--ease-out-strong) infinite; flex-shrink: 0; }
.nxai-title-dot.offline { background: #6b7280; animation: none; }
.nxai-close {
  background: none; border: none; color: var(--body-dim); cursor: pointer; font-size: 14px; padding: 4px;
  transition: color 0.2s var(--ease-out-strong), transform 0.15s var(--ease-out-strong);
}
.nxai-close:hover { color: var(--body-light); }
.nxai-close:active { transform: scale(0.9); }
.nxai-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; overflow-y: auto; position: relative; z-index: 1; }
.nxai-label {
  font-family: 'Chakra Petch', monospace; text-transform: uppercase; letter-spacing: 0.08em;
  font-size: 10.5px; color: var(--body-dim); margin-top: 10px;
}
.nxai-textarea {
  width: 100%; background: rgba(255,255,255,0.04); border: 1px solid var(--glass-border);
  border-radius: 10px; padding: 10px 12px; color: var(--body-light); font-family: 'Manrope', sans-serif;
  font-size: 13px; resize: vertical; transition: border-color 0.25s var(--ease-out-strong), box-shadow 0.25s var(--ease-out-strong);
}
.nxai-textarea:focus { outline: none; border-color: var(--accent-from); box-shadow: 0 0 0 3px rgba(255,122,26,0.18); }
.nxai-textarea::placeholder { color: rgba(229,229,229,0.4); }
.nxai-textarea:disabled { opacity: 0.6; }
.nxai-dropzone {
  position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 6px; padding: 18px 12px; border-radius: 12px; border: 1px dashed var(--glass-border);
  background: rgba(255,255,255,0.02); cursor: pointer; text-align: center;
  transition: transform 0.25s var(--ease-out-expo), border-color 0.25s var(--ease-out-strong), background 0.25s var(--ease-out-strong);
}
.nxai-dropzone:hover { transform: translateY(-2px); border-color: var(--accent-from); background: rgba(255,122,26,0.06); }
.nxai-dropzone:active { transform: scale(0.98); }
.nxai-dropzone input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.nxai-dropzone-text { font-family: 'Manrope', sans-serif; font-size: 12px; color: var(--body-dim); }
.nxai-dropzone-text strong { color: var(--body-light); }
.nxai-dropzone-count {
  font-family: 'Chakra Petch', monospace; font-size: 11px; letter-spacing: 0.05em; font-weight: 700;
  background: linear-gradient(90deg, var(--accent-from), var(--accent-to));
  -webkit-background-clip: text; background-clip: text; color: transparent; margin-top: 2px;
}
.nxai-thumbs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.nxai-thumb { width: 42px; height: 42px; border-radius: 8px; object-fit: cover; border: 1px solid var(--glass-border); }
.nxai-btn-primary {
  margin-top: 14px; padding: 12px 16px; border: none; border-radius: 10px;
  font-family: 'Montserrat', sans-serif; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em;
  font-size: 12px; color: var(--night); background: linear-gradient(90deg, var(--accent-from), var(--accent-to));
  cursor: pointer; box-shadow: 0 6px 20px rgba(255,122,26,0.25);
  transition: transform 0.25s var(--ease-out-expo), box-shadow 0.25s var(--ease-out-strong);
}
.nxai-btn-primary:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(255,122,26,0.4); }
.nxai-btn-primary:active:not(:disabled) { transform: scale(0.97); }
.nxai-btn-primary:disabled { opacity: 0.55; cursor: default; }
.nxai-btn-secondary {
  margin-top: 12px; padding: 10px 14px; border-radius: 10px; border: 1px solid var(--glass-border);
  background: rgba(255,255,255,0.03); color: var(--body-light); font-family: 'Manrope', sans-serif;
  font-weight: 600; font-size: 12.5px; cursor: pointer;
  transition: background 0.25s var(--ease-out-strong), transform 0.2s var(--ease-out-expo);
}
.nxai-btn-secondary:hover { background: rgba(255,255,255,0.08); }
.nxai-btn-secondary:active { transform: scale(0.97); }
.nxai-error { color: var(--status-red); font-size: 12px; margin-top: 4px; font-family: 'Manrope', sans-serif; }
.nxai-hint { font-size: 11px; color: var(--body-dim); opacity: 0.8; margin-top: 8px; }
.nxai-banner {
  padding: 10px 12px; border-radius: 10px; font-family: 'Chakra Petch', monospace;
  font-size: 11.5px; letter-spacing: 0.03em; text-transform: uppercase;
  background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.35); color: var(--status-green);
}
.nxai-review-group { margin-top: 12px; }
.nxai-review-title {
  font-family: 'Chakra Petch', monospace; text-transform: uppercase; letter-spacing: 0.06em;
  font-size: 10.5px; font-weight: 700; margin-bottom: 4px;
}
.nxai-review-title.ok { color: var(--status-green); }
.nxai-review-title.warn { color: var(--accent-to); }
.nxai-review-title.blocking { color: var(--status-red); }
.nxai-review-list { margin: 0; padding-left: 16px; font-size: 12.5px; color: var(--body-dim); font-family: 'Manrope', sans-serif; }
@media (prefers-reduced-motion: reduce) {
  .nxai-fab, .nxai-panel, .nxai-btn-primary, .nxai-btn-secondary, .nxai-dropzone, .nxai-status-dot, .nxai-title-dot {
    animation: none !important;
    transition: opacity 0.2s linear !important;
  }
  .nxai-fab:hover, .nxai-fab:active, .nxai-btn-primary:hover, .nxai-btn-primary:active,
  .nxai-btn-secondary:active, .nxai-dropzone:hover, .nxai-dropzone:active {
    transform: none !important;
  }
}
`;

function UploadIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="nxai-upload-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ff7a1a" />
          <stop offset="100%" stopColor="#ffb300" />
        </linearGradient>
      </defs>
      <path
        d="M12 15.5V4M12 4L7.5 8.5M12 4l4.5 4.5"
        stroke="url(#nxai-upload-grad)"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M4 16v2.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V16"
        stroke="url(#nxai-upload-grad)"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function FloatingAgentWidget({
  backendApiBaseUrl,
  dashboardApiBaseUrl = "",
  onAutofill,
}: FloatingAgentWidgetProps) {
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState("");
  const [stage, setStage] = useState<Stage>("form");
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState<ReviewReport | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [thumbUrls, setThumbUrls] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${backendApiBaseUrl}/health`)
      .then((res) => {
        if (!cancelled) setBackendOnline(res.ok);
      })
      .catch(() => {
        if (!cancelled) setBackendOnline(false);
      });
    return () => {
      cancelled = true;
    };
  }, [backendApiBaseUrl]);

  useEffect(() => {
    const urls = selectedFiles.map((f) => URL.createObjectURL(f));
    setThumbUrls(urls);
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [selectedFiles]);

  function handleFileChange() {
    const files = fileInputRef.current?.files;
    setSelectedFiles(files ? Array.from(files) : []);
  }

  async function uploadImage(file: File): Promise<UploadedAsset> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("altText", file.name.replace(/\.[^.]+$/, ""));

    const res = await fetch(`${dashboardApiBaseUrl}/api/v1/admin/assets`, {
      method: "POST",
      credentials: "include",
      body: formData,
    });
    if (!res.ok) {
      throw new Error(`Image upload failed for "${file.name}" (${res.status})`);
    }
    return res.json();
  }

  async function handleSubmit() {
    if (!summary.trim()) {
      setError("Please enter a project summary first.");
      return;
    }

    setStage("loading");
    setError(null);

    try {
      const extractRes = await fetch(`${backendApiBaseUrl}/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ summary }),
      });
      if (!extractRes.ok) {
        const body = await extractRes.json().catch(() => ({}));
        throw new Error(body.detail || `Extraction failed (${extractRes.status})`);
      }
      const extracted: ExtractResponse = await extractRes.json();

      const uploadedAssets: UploadedAsset[] = [];
      for (const file of selectedFiles) {
        try {
          uploadedAssets.push(await uploadImage(file));
        } catch (uploadErr) {
          extracted.review.warnings.push(
            uploadErr instanceof Error ? uploadErr.message : `Failed to upload ${file.name}`
          );
        }
      }

      onAutofill({
        service: extracted.service,
        title: extracted.payload.title,
        industry: extracted.payload.industry,
        description: extracted.payload.description,
        tags: extracted.payload.tags,
        caseStudy: extracted.payload.caseStudy,
        uploadedAssets,
      });

      setReview(extracted.review);
      setStage("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setStage("error");
    }
  }

  function reset() {
    setSummary("");
    setReview(null);
    setError(null);
    setStage("form");
    setSelectedFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const statusLabel = backendOnline === false ? "offline" : "";

  return (
    <div className="nxai-root">
      <style>{STYLE_SHEET}</style>

      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close AI project assistant" : "Open AI project assistant"}
        className="nxai-fab"
      >
        {open ? (
          <span className="nxai-fab-glyph">✕</span>
        ) : (
          <img src="/nexoryn-logo.png" alt="Nexoryn" className="nxai-fab-img" />
        )}
        {!open && <span className={`nxai-status-dot ${statusLabel}`} title={backendOnline === false ? "Agent backend unreachable" : "Agent backend ready"} />}
      </button>

      {open && (
        <div className="nxai-panel">
          <div className="nxai-grain" />

          <div className="nxai-header">
            <span className="nxai-title">
              <span className={`nxai-title-dot ${statusLabel}`} />
              AI Project Assistant
            </span>
            <button onClick={() => setOpen(false)} className="nxai-close" aria-label="Close">
              ✕
            </button>
          </div>

          {(stage === "form" || stage === "loading" || stage === "error") && (
            <div className="nxai-body">
              <label className="nxai-label">Project Summary</label>
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="Describe the project: client, industry, location, tech stack, what you built, how long it took..."
                rows={7}
                className="nxai-textarea"
                disabled={stage === "loading"}
              />

              <label className="nxai-label">Project Images</label>
              <label className="nxai-dropzone">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  disabled={stage === "loading"}
                  onChange={handleFileChange}
                />
                <UploadIcon />
                <span className="nxai-dropzone-text">
                  <strong>Click to upload</strong> or drag images here
                </span>
                {selectedFiles.length > 0 && (
                  <span className="nxai-dropzone-count">
                    {selectedFiles.length} image{selectedFiles.length === 1 ? "" : "s"} selected
                  </span>
                )}
              </label>
              {thumbUrls.length > 0 && (
                <div className="nxai-thumbs">
                  {thumbUrls.map((url, i) => (
                    <img key={i} src={url} alt="" className="nxai-thumb" />
                  ))}
                </div>
              )}

              {error && <div className="nxai-error">{error}</div>}

              <button onClick={handleSubmit} disabled={stage === "loading"} className="nxai-btn-primary">
                {stage === "loading" ? "Filling in the form..." : "Fill Form"}
              </button>

              <p className="nxai-hint">
                This fills in the fields above for you to review. It never
                clicks Save Project — that's always your call.
              </p>
            </div>
          )}

          {stage === "done" && review && (
            <div className="nxai-body">
              <div className="nxai-banner">
                Fields filled in above — review, then click Save Project yourself.
              </div>

              {review.blocking.length > 0 && (
                <div className="nxai-review-group">
                  <div className="nxai-review-title blocking">Required — still empty</div>
                  <ul className="nxai-review-list">
                    {review.blocking.map((item, i) => <li key={i}>{item}</li>)}
                  </ul>
                </div>
              )}
              {review.warnings.length > 0 && (
                <div className="nxai-review-group">
                  <div className="nxai-review-title warn">Missing / needs review</div>
                  <ul className="nxai-review-list">
                    {review.warnings.map((item, i) => <li key={i}>{item}</li>)}
                  </ul>
                </div>
              )}
              {review.ok.length > 0 && (
                <div className="nxai-review-group">
                  <div className="nxai-review-title ok">Filled in</div>
                  <ul className="nxai-review-list">
                    {review.ok.map((item, i) => <li key={i}>{item}</li>)}
                  </ul>
                </div>
              )}

              <button onClick={reset} className="nxai-btn-secondary">
                Start another project
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
