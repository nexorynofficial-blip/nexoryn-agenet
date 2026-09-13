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
 */
import { useRef, useState, type CSSProperties } from "react";

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
  const fileInputRef = useRef<HTMLInputElement>(null);

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

      const files = fileInputRef.current?.files;
      const uploadedAssets: UploadedAsset[] = [];
      if (files && files.length > 0) {
        for (const file of Array.from(files)) {
          try {
            uploadedAssets.push(await uploadImage(file));
          } catch (uploadErr) {
            extracted.review.warnings.push(
              uploadErr instanceof Error ? uploadErr.message : `Failed to upload ${file.name}`
            );
          }
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
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close AI project assistant" : "Open AI project assistant"}
        style={styles.fab}
      >
        {open ? (
          <span style={styles.fabCloseGlyph}>✕</span>
        ) : (
          <img src="/nexoryn-logo.png" alt="Nexoryn" style={styles.fabImg} />
        )}
      </button>

      {open && (
        <div style={styles.panel}>
          <div style={styles.header}>
            <strong>AI Project Assistant</strong>
            <button onClick={() => setOpen(false)} style={styles.closeBtn} aria-label="Close">
              ✕
            </button>
          </div>

          {(stage === "form" || stage === "loading" || stage === "error") && (
            <div style={styles.body}>
              <label style={styles.label}>Project summary</label>
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="Describe the project: client, industry, location, tech stack, what you built, how long it took..."
                rows={8}
                style={styles.textarea}
                disabled={stage === "loading"}
              />

              <label style={styles.label}>Project images</label>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                disabled={stage === "loading"}
                style={styles.fileInput}
              />

              {error && <div style={styles.error}>{error}</div>}

              <button onClick={handleSubmit} disabled={stage === "loading"} style={styles.primaryBtn}>
                {stage === "loading" ? "Filling in the form..." : "Fill Form"}
              </button>

              <p style={styles.hint}>
                This fills in the fields above for you to review. It never
                clicks Save Project — that's always your call.
              </p>
            </div>
          )}

          {stage === "done" && review && (
            <div style={styles.body}>
              <div style={styles.successBanner}>
                Fields filled in above — review everything, then click
                Save Project yourself when ready.
              </div>

              {review.blocking.length > 0 && (
                <ReviewSection title="Required — still empty" items={review.blocking} tone="blocking" />
              )}
              {review.warnings.length > 0 && (
                <ReviewSection title="Missing / needs review" items={review.warnings} tone="warning" />
              )}
              {review.ok.length > 0 && (
                <ReviewSection title="Filled in" items={review.ok} tone="ok" />
              )}

              <button onClick={reset} style={styles.secondaryBtn}>
                Start another project
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function ReviewSection({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "ok" | "warning" | "blocking";
}) {
  const color = tone === "ok" ? "#1a7f37" : tone === "warning" ? "#9a6700" : "#cf222e";
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontWeight: 600, fontSize: 13, color, marginBottom: 4 }}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  fab: {
    position: "fixed",
    bottom: 24,
    right: 24,
    width: 56,
    height: 56,
    borderRadius: "50%",
    border: "none",
    background: "#111827",
    color: "#fff",
    cursor: "pointer",
    boxShadow: "0 4px 14px rgba(0,0,0,0.25)",
    zIndex: 1000,
    padding: 0,
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  fabImg: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
    display: "block",
  },
  fabCloseGlyph: {
    fontSize: 20,
    lineHeight: 1,
  },
  panel: {
    position: "fixed",
    bottom: 92,
    right: 24,
    width: 360,
    maxHeight: "70vh",
    overflowY: "auto",
    background: "#fff",
    borderRadius: 12,
    boxShadow: "0 8px 30px rgba(0,0,0,0.2)",
    zIndex: 1000,
    display: "flex",
    flexDirection: "column",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    borderBottom: "1px solid #eee",
  },
  closeBtn: {
    border: "none",
    background: "transparent",
    cursor: "pointer",
    fontSize: 14,
  },
  body: {
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  label: {
    fontSize: 12,
    fontWeight: 600,
    color: "#374151",
    marginTop: 8,
  },
  textarea: {
    width: "100%",
    padding: 8,
    borderRadius: 8,
    border: "1px solid #d1d5db",
    fontSize: 13,
    resize: "vertical",
  },
  fileInput: {
    fontSize: 12,
  },
  primaryBtn: {
    marginTop: 12,
    padding: "10px 14px",
    borderRadius: 8,
    border: "none",
    background: "#111827",
    color: "#fff",
    fontWeight: 600,
    cursor: "pointer",
  },
  secondaryBtn: {
    marginTop: 12,
    padding: "10px 14px",
    borderRadius: 8,
    border: "1px solid #d1d5db",
    background: "#fff",
    color: "#111827",
    fontWeight: 600,
    cursor: "pointer",
  },
  error: {
    color: "#cf222e",
    fontSize: 12,
    marginTop: 4,
  },
  hint: {
    fontSize: 11,
    color: "#6b7280",
    marginTop: 8,
  },
  successBanner: {
    background: "#dcfce7",
    color: "#166534",
    padding: "8px 12px",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
  },
};
