import { useState, useRef, useEffect } from "react";

interface Props {
  onSubmit: (question: string) => void;
  loading: boolean;
}

export function ChatInput({ onSubmit, loading }: Props) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const q = value.trim();
    if (!q || loading) return;
    onSubmit(q);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 140) + "px";
    }
  }, [value]);

  const isActive = focused || loading;

  return (
    <div style={{
      background: "var(--surface)",
      border: `1.5px solid ${isActive ? (loading ? "rgba(15,122,255,0.35)" : "var(--border-strong)") : "var(--border)"}`,
      borderRadius: 16,
      padding: "12px 14px 12px 18px",
      display: "flex",
      alignItems: "flex-end",
      gap: 10,
      transition: "border-color 0.18s ease, box-shadow 0.18s ease",
      boxShadow: isActive
        ? loading
          ? "0 0 0 3px rgba(15,122,255,0.08), var(--shadow-md)"
          : "0 0 0 3px rgba(0,0,0,0.04), var(--shadow-md)"
        : "var(--shadow-sm)",
    }}>

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder={loading ? "Analysiere…" : "Stelle eine Frage zu deinen Daten…"}
        rows={1}
        disabled={loading}
        style={{
          flex: 1,
          resize: "none",
          outline: "none",
          background: "transparent",
          border: "none",
          color: "var(--text-primary)",
          fontFamily: "var(--font-sans)",
          fontSize: 14.5,
          lineHeight: 1.6,
          minHeight: 26,
          maxHeight: 140,
          overflow: "auto",
          letterSpacing: "-0.01em",
          opacity: loading ? 0.5 : 1,
        }}
      />

      {/* Right side: hint + send button */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {/* Keyboard hint */}
        {value.trim() && !loading && (
          <span style={{
            fontSize: 11,
            color: "var(--text-tertiary)",
            fontFamily: "var(--font-mono)",
            whiteSpace: "nowrap",
            opacity: focused ? 1 : 0,
            transition: "opacity 0.15s",
          }}>
            ↵ senden
          </span>
        )}

        {/* Send / loading button */}
        <button
          onClick={submit}
          disabled={!value.trim() || loading}
          style={{
            width: 34,
            height: 34,
            flexShrink: 0,
            borderRadius: 10,
            border: "none",
            background: loading
              ? "var(--bg-hover)"
              : !value.trim()
                ? "var(--bg-hover)"
                : "var(--text-primary)",
            cursor: !value.trim() || loading ? "default" : "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "all 0.18s ease",
            transform: value.trim() && !loading ? "scale(1)" : "scale(0.95)",
            opacity: !value.trim() && !loading ? 0.35 : 1,
          }}
          onMouseEnter={e => {
            if (value.trim() && !loading) {
              e.currentTarget.style.transform = "scale(1.06)";
              e.currentTarget.style.background = "#111";
            }
          }}
          onMouseLeave={e => {
            if (value.trim() && !loading) {
              e.currentTarget.style.transform = "scale(1)";
              e.currentTarget.style.background = "var(--text-primary)";
            }
          }}
        >
          {loading ? (
            <div style={{
              width: 14, height: 14,
              border: "1.5px solid var(--border-strong)",
              borderTop: "1.5px solid var(--accent-blue)",
              borderRadius: "50%",
              animation: "spin 0.75s linear infinite",
            }}/>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          )}
        </button>
      </div>

      <style>{`
        textarea::placeholder { color: var(--text-placeholder); }
      `}</style>
    </div>
  );
}
