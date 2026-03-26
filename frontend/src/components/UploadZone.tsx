import { useRef, useState } from "react";
import { api } from "../api/client";
import type { UploadResponse } from "../types";

interface Props {
  onUploaded: (result: UploadResponse) => void;
}

export function UploadZone({ onUploaded }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [progress, setProgress] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setLoading(true);
    setProgress(true);
    setError(null);
    try {
      const result = await api.upload(file);
      onUploaded(result);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Upload fehlgeschlagen.");
      setProgress(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ width: "100%", maxWidth: 480 }}>
      <div
        onClick={() => !loading && inputRef.current?.click()}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files[0];
          if (f) handleFile(f);
        }}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        style={{
          border: `1.5px dashed ${dragOver ? "var(--accent-blue)" : "var(--border-strong)"}`,
          borderRadius: 20,
          padding: "44px 40px 40px",
          textAlign: "center",
          cursor: loading ? "wait" : "pointer",
          background: dragOver ? "var(--accent-blue-dim)" : "var(--bg-subtle)",
          transition: "all 0.2s ease",
          position: "relative",
          overflow: "hidden",
        }}
        onMouseEnter={e => {
          if (!loading && !dragOver) {
            e.currentTarget.style.background = "var(--bg-hover)";
            e.currentTarget.style.borderColor = "var(--border-strong)";
          }
        }}
        onMouseLeave={e => {
          if (!dragOver) {
            e.currentTarget.style.background = loading ? "var(--bg-subtle)" : "var(--bg-subtle)";
            e.currentTarget.style.borderColor = dragOver ? "var(--accent-blue)" : "var(--border-strong)";
          }
        }}
      >
        {/* Progress bar */}
        {progress && (
          <div style={{
            position: "absolute",
            bottom: 0, left: 0, right: 0,
            height: 2,
            background: "var(--border)",
            borderRadius: "0 0 20px 20px",
            overflow: "hidden",
          }}>
            <div style={{
              height: "100%",
              background: "var(--accent-blue)",
              borderRadius: 999,
              animation: "progress-bar 2s ease-out forwards",
            }}/>
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
            {/* Spinning ring */}
            <div style={{
              width: 40, height: 40,
              border: "2px solid var(--border)",
              borderTop: "2px solid var(--accent-blue)",
              borderRadius: "50%",
              animation: "spin 0.75s linear infinite",
            }}/>
            <div>
              <p style={{
                fontFamily: "var(--font-sans)",
                fontWeight: 500,
                fontSize: 14,
                color: "var(--text-primary)",
                marginBottom: 4,
              }}>
                Wird verarbeitet…
              </p>
              <p style={{
                fontSize: 12.5,
                color: "var(--text-tertiary)",
                fontFamily: "var(--font-mono)",
              }}>
                Tabellen werden erkannt
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Upload icon */}
            <div style={{
              width: 52, height: 52,
              margin: "0 auto 20px",
              background: dragOver ? "rgba(15,122,255,0.10)" : "var(--bg)",
              border: `1px solid ${dragOver ? "var(--accent-blue-border)" : "var(--border)"}`,
              borderRadius: 14,
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "all 0.2s",
              boxShadow: "var(--shadow-sm)",
            }}>
              <svg
                width="22" height="22" viewBox="0 0 24 24" fill="none"
                stroke={dragOver ? "var(--accent-blue)" : "var(--text-secondary)"}
                strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                style={{ transition: "stroke 0.2s" }}
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>

            <p style={{
              fontFamily: "var(--font-sans)",
              fontWeight: 600,
              fontSize: 15.5,
              color: "var(--text-primary)",
              marginBottom: 6,
              letterSpacing: "-0.02em",
            }}>
              {dragOver ? "Loslassen zum Hochladen" : "Datei ablegen"}
            </p>
            <p style={{
              fontSize: 13.5,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
            }}>
              oder{" "}
              <span style={{
                color: "var(--accent-blue)",
                fontWeight: 500,
                textDecoration: "underline",
                textDecorationColor: "rgba(15,122,255,0.3)",
                textUnderlineOffset: 3,
              }}>
                klicken zum Auswählen
              </span>
            </p>
          </>
        )}

        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.xls,.db,.sqlite,.sql"
          style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
      </div>

      {error && (
        <div
          className="anim-slide-down"
          style={{
            marginTop: 12,
            padding: "10px 14px",
            background: "var(--red-bg)",
            border: "1px solid rgba(208,58,47,0.18)",
            borderRadius: 10,
            fontSize: 13,
            color: "var(--red)",
            fontFamily: "var(--font-sans)",
            display: "flex",
            alignItems: "center",
            gap: 7,
          }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {error}
        </div>
      )}
    </div>
  );
}
