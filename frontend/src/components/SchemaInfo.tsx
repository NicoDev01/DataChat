import { useState } from "react";
import type { UploadResponse } from "../types";

interface Props {
  upload: UploadResponse;
}

export function SchemaInfo({ upload }: Props) {
  const [expanded, setExpanded] = useState(false);

  const displayName = upload.filename
    ? upload.filename.replace(/\.[^.]+$/, "")
    : "Datei";
  const ext = upload.filename?.match(/\.[^.]+$/)?.[0] ?? "";

  return (
    <div
      className="anim-fade-up"
      style={{
        background: "var(--bg)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        marginBottom: 20,
        overflow: "hidden",
        boxShadow: "var(--shadow-sm)",
        transition: "box-shadow 0.2s ease",
      }}
      onMouseEnter={e => (e.currentTarget.style.boxShadow = "var(--shadow-md)")}
      onMouseLeave={e => (e.currentTarget.style.boxShadow = "var(--shadow-sm)")}
    >
      {/* ── Header row ── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "14px 18px",
        gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>

          {/* File icon */}
          <div style={{
            width: 36, height: 36, flexShrink: 0,
            background: "var(--bg-subtle)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
          </div>

          <div style={{ minWidth: 0 }}>
            {/* Filename */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{
                fontFamily: "var(--font-sans)",
                fontWeight: 700,
                fontSize: 15,
                color: "var(--text-primary)",
                letterSpacing: "-0.03em",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: 320,
              }}>
                {displayName}
              </span>
              {ext && (
                <span style={{
                  fontSize: 11,
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-tertiary)",
                  background: "var(--bg-hover)",
                  border: "1px solid var(--border)",
                  borderRadius: 4,
                  padding: "1px 5px",
                  letterSpacing: "0.02em",
                  flexShrink: 0,
                }}>
                  {ext}
                </span>
              )}
            </div>

            {/* Stats */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
              <span style={{ fontSize: 12, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                <span style={{ color: "var(--text-secondary)", fontWeight: 600 }}>{upload.table_count}</span>
                {" "}{upload.table_count === 1 ? "Tabelle" : "Tabellen"}
              </span>
              <span style={{ color: "var(--border-strong)", fontSize: 9 }}>●</span>
              <span style={{ fontSize: 12, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                <span style={{ color: "var(--text-secondary)", fontWeight: 600 }}>{upload.row_count.toLocaleString("de-DE")}</span>
                {" "}Zeilen
              </span>
            </div>
          </div>
        </div>

        {/* Schema toggle */}
        <button
          onClick={() => setExpanded(v => !v)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            fontSize: 12,
            fontWeight: 500,
            color: expanded ? "var(--text-primary)" : "var(--text-secondary)",
            background: expanded ? "var(--bg-hover)" : "transparent",
            border: "1px solid " + (expanded ? "var(--border-strong)" : "var(--border)"),
            borderRadius: 999,
            padding: "5px 12px",
            cursor: "pointer",
            fontFamily: "var(--font-sans)",
            transition: "all 0.15s ease",
            flexShrink: 0,
            letterSpacing: "-0.01em",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = "var(--bg-hover)";
            e.currentTarget.style.borderColor = "var(--border-strong)";
            e.currentTarget.style.color = "var(--text-primary)";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = expanded ? "var(--bg-hover)" : "transparent";
            e.currentTarget.style.borderColor = expanded ? "var(--border-strong)" : "var(--border)";
            e.currentTarget.style.color = expanded ? "var(--text-primary)" : "var(--text-secondary)";
          }}
        >
          <svg
            width="10" height="10" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
            style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}
          >
            <polyline points="6 9 12 15 18 9"/>
          </svg>
          Schema
        </button>
      </div>

      {/* ── Table name pills ── */}
      <div style={{ padding: "0 18px 14px", display: "flex", flexWrap: "wrap", gap: 6 }}>
        {upload.table_names.map(name => (
          <span key={name} style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "4px 11px",
            borderRadius: 999,
            border: "1px solid var(--border)",
            background: "var(--bg-subtle)",
            fontSize: 12,
            fontFamily: "var(--font-mono)",
            color: "var(--text-secondary)",
            letterSpacing: "0.01em",
          }}>
            {name}
          </span>
        ))}
      </div>

      {/* ── Schema body ── */}
      {expanded && (
        <div
          className="anim-slide-down"
          style={{
            borderTop: "1px solid var(--border)",
            background: "var(--bg-subtle)",
          }}
        >
          <pre style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11.5,
            color: "var(--text-secondary)",
            lineHeight: 1.75,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            maxHeight: 280,
            overflowY: "auto",
            margin: 0,
            padding: "14px 18px",
          }}>
            {upload.schema_description}
          </pre>
        </div>
      )}
    </div>
  );
}
