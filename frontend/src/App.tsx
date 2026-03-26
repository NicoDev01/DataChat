import { useState, useEffect } from "react";
import { api } from "./api/client";
import type { UploadResponse, QueryResponse } from "./types";
import { UploadZone } from "./components/UploadZone";
import { SchemaInfo } from "./components/SchemaInfo";
import { ChatInput } from "./components/ChatInput";
import { AnswerCard } from "./components/AnswerCard";

// ── Demo data ─────────────────────────────────────────────
// 3 looping demo scenarios — each shows: question → answer stat + mini chart
const DEMOS = [
  {
    question: "Welcher Monat hatte den höchsten Umsatz?",
    stat: "€ 284.900",
    label: "November 2024",
    tag: "Top-Monat",
    bars: [62, 71, 58, 80, 74, 55, 68, 76, 83, 90, 100, 87],
    barLabels: ["J","F","M","A","M","J","J","A","S","O","N","D"],
    highlightIdx: 10,
  },
  {
    question: "Wie viele Kunden haben mehr als 3x bestellt?",
    stat: "1.847",
    label: "Stammkunden",
    tag: "Segment",
    bars: [22, 34, 18, 40, 55, 63, 71, 58, 44, 38],
    barLabels: ["<1","1","2","3","4","5","6","7","8","9+"],
    highlightIdx: 5,
  },
  {
    question: "Welches Produkt hat die höchste Retourenquote?",
    stat: "18,4 %",
    label: "Produkt XR-7",
    tag: "Ausreißer",
    bars: [5, 8, 6, 12, 7, 18, 9, 4, 11, 7],
    barLabels: ["A","B","C","D","E","F","G","H","I","J"],
    highlightIdx: 5,
  },
];

const CAPABILITIES = [
  { label: "Trends analysieren",        mono: "GROUP BY monat" },
  { label: "Top-N Rankings",            mono: "ORDER BY … LIMIT 10" },
  { label: "Ausreißer finden",          mono: "WHERE wert > AVG(…)" },
  { label: "Tabellen verknüpfen",       mono: "JOIN ON id" },
  { label: "Aggregationen",             mono: "SUM · AVG · COUNT" },
  { label: "Zeitreihen",                mono: "strftime('%Y-%m', …)" },
  { label: "Segmentierung",             mono: "CASE WHEN … THEN" },
  { label: "Pivot-Auswertungen",        mono: "GROUP BY a, b" },
  { label: "Duplikate erkennen",        mono: "HAVING COUNT(*) > 1" },
  { label: "Prozentwerte berechnen",    mono: "val * 100.0 / SUM(val)" },
  { label: "Fehlende Werte finden",     mono: "WHERE spalte IS NULL" },
  { label: "Kumulative Summen",         mono: "SUM(…) OVER (ORDER BY …)" },
];

// ── Demo component ────────────────────────────────────────
function DemoConversation() {
  const [demoIdx, setDemoIdx] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [showThinking, setShowThinking] = useState(false);

  useEffect(() => {
    setShowAnswer(false);
    setShowThinking(false);
    const t1 = setTimeout(() => setShowThinking(true), 900);
    const t2 = setTimeout(() => { setShowThinking(false); setShowAnswer(true); }, 2000);
    const t3 = setTimeout(() => {
      setShowAnswer(false);
      setDemoIdx(i => (i + 1) % DEMOS.length);
    }, 5200);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [demoIdx]);

  const demo = DEMOS[demoIdx];
  const maxBar = Math.max(...demo.bars);

  return (
    <div style={{ width: "100%", maxWidth: 480 }}>
      {/* Fixed-height card — no layout shift */}
      <div style={{
        background: "var(--bg)",
        border: "1px solid var(--border)",
        borderRadius: 20,
        overflow: "hidden",
        boxShadow: "var(--shadow-lg)",
        /* Fixed total height = padding-top(24) + question(~52) + gap(16) + answer(~148) + padding-bot(24) = 264 */
        height: 296,
        display: "flex",
        flexDirection: "column",
      }}>
        <div style={{
          flex: 1,
          padding: "24px 24px 20px",
          display: "flex",
          flexDirection: "column",
          gap: 16,
          overflow: "hidden",
        }}>

          {/* ── Question — always visible, fades on new demo ── */}
          <div
            key={`q-${demoIdx}`}
            className="demo-bubble"
            style={{ display: "flex", alignItems: "flex-start", gap: 10, flexShrink: 0 }}
          >
            <div style={{
              width: 24, height: 24, flexShrink: 0,
              background: "var(--text-primary)",
              borderRadius: 7,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <span style={{
              fontSize: 13.5,
              color: "var(--text-primary)",
              fontFamily: "var(--font-sans)",
              fontWeight: 600,
              lineHeight: 1.45,
              letterSpacing: "-0.02em",
              paddingTop: 2,
            }}>
              {demo.question}
            </span>
          </div>

          {/* ── Response area — fixed height slot, no shift ── */}
          <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>

            {/* Thinking dots */}
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", alignItems: "flex-start", gap: 6,
              opacity: showThinking ? 1 : 0,
              transform: showThinking ? "translateY(0)" : "translateY(6px)",
              transition: "opacity 0.3s ease, transform 0.3s ease",
              pointerEvents: "none",
            }}>
              {[0,1,2].map(i => (
                <div key={i} style={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: "var(--border-strong)",
                  animation: showThinking ? `blink-cursor 1s ease-in-out ${i * 0.18}s infinite` : "none",
                  marginTop: 2,
                }}/>
              ))}
            </div>

            {/* Answer */}
            <div style={{
              position: "absolute", inset: 0,
              opacity: showAnswer ? 1 : 0,
              transform: showAnswer ? "translateY(0)" : "translateY(12px)",
              transition: "opacity 0.45s ease, transform 0.45s cubic-bezier(0.16,1,0.3,1)",
              pointerEvents: showAnswer ? "auto" : "none",
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}>
              {/* Stat row */}
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: 34,
                  fontWeight: 800,
                  letterSpacing: "-0.04em",
                  color: "var(--text-primary)",
                  lineHeight: 1,
                }}>
                  {demo.stat}
                </span>
                <span style={{
                  fontSize: 11,
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-tertiary)",
                  background: "var(--bg-hover)",
                  border: "1px solid var(--border)",
                  borderRadius: 999,
                  padding: "2px 9px",
                  fontWeight: 500,
                  whiteSpace: "nowrap",
                  letterSpacing: "0.01em",
                }}>
                  {demo.tag}
                </span>
              </div>

              <p style={{
                fontSize: 12,
                color: "var(--text-tertiary)",
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.01em",
                lineHeight: 1,
              }}>
                {demo.label}
              </p>

              {/* Bar chart — fixed height 56px */}
              <div style={{
                display: "flex",
                alignItems: "flex-end",
                gap: 3,
                height: 56,
                marginTop: "auto",
              }}>
                {demo.bars.map((val, bi) => {
                  const isHigh = bi === demo.highlightIdx;
                  const h = Math.max(4, Math.round((val / maxBar) * 44));
                  return (
                    <div key={bi} style={{
                      flex: 1,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 4,
                      height: "100%",
                      justifyContent: "flex-end",
                    }}>
                      <div
                        className={showAnswer ? "demo-bar" : ""}
                        style={{
                          width: "100%",
                          height: h,
                          background: isHigh ? "var(--text-primary)" : "var(--bg-active)",
                          borderRadius: "2px 2px 0 0",
                          animationDelay: showAnswer ? `${bi * 0.025}s` : "0s",
                        }}
                      />
                      <span style={{
                        fontSize: 8,
                        color: isHigh ? "var(--text-primary)" : "var(--text-tertiary)",
                        fontFamily: "var(--font-mono)",
                        fontWeight: isHigh ? 700 : 400,
                        lineHeight: 1,
                        letterSpacing: 0,
                      }}>
                        {demo.barLabels[bi]}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

          </div>
        </div>

        {/* Progress strip */}
        <div style={{ height: 2, background: "var(--border)", flexShrink: 0, position: "relative", overflow: "hidden" }}>
          <div
            key={`p-${demoIdx}-${showAnswer ? "a" : showThinking ? "t" : "q"}`}
            style={{
              position: "absolute", top: 0, left: 0, height: "100%",
              background: "var(--text-primary)", borderRadius: 999,
              animation: showAnswer
                ? "progress-bar 3.8s linear forwards"
                : showThinking
                  ? "progress-bar 1.2s ease-out forwards"
                  : "none",
              width: (!showAnswer && !showThinking) ? "0%" : undefined,
            }}
          />
        </div>
      </div>

      {/* Dot indicators */}
      <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 16 }}>
        {DEMOS.map((_, i) => (
          <div key={i} style={{
            width: i === demoIdx ? 20 : 6,
            height: 6,
            borderRadius: 999,
            background: i === demoIdx ? "var(--text-primary)" : "var(--border-strong)",
            transition: "all 0.35s cubic-bezier(0.16,1,0.3,1)",
          }}/>
        ))}
      </div>
    </div>
  );
}

interface HistoryEntry {
  question: string;
  result: QueryResponse;
}

export default function App() {
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUploaded = (result: UploadResponse) => {
    setUpload(result);
    setHistory([]);
    setError(null);
  };

  const handleReset = () => {
    setUpload(null);
    setHistory([]);
    setError(null);
  };

  const handleQuestion = async (question: string) => {
    if (!upload) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.query(upload.session_id, question);
      setHistory((prev) => [{ question, result }, ...prev]);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Anfrage fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", flexDirection: "column" }}>

      {/* ── Header ── */}
      <header style={{
        borderBottom: "1px solid var(--border)",
        background: "rgba(255,255,255,0.90)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        padding: "0 48px",
        height: 52,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Logo mark */}
          <div style={{
            width: 26, height: 26,
            background: "var(--text-primary)",
            borderRadius: 7,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <rect x="1" y="1" width="4.5" height="4.5" rx="1" fill="white" fillOpacity="0.9"/>
              <rect x="7.5" y="1" width="4.5" height="4.5" rx="1" fill="white" fillOpacity="0.45"/>
              <rect x="1" y="7.5" width="4.5" height="4.5" rx="1" fill="white" fillOpacity="0.45"/>
              <rect x="7.5" y="7.5" width="4.5" height="4.5" rx="1" fill="white" fillOpacity="0.9"/>
            </svg>
          </div>
          <span style={{
            fontFamily: "var(--font-sans)",
            fontWeight: 600,
            fontSize: 15,
            color: "var(--text-primary)",
            letterSpacing: "-0.02em",
          }}>
            DataChat
          </span>
        </div>

        {upload && (
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            {/* Live indicator */}
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <div style={{
                width: 7, height: 7, borderRadius: "50%",
                background: "var(--green)",
                animation: "pulse-ring 2.5s ease-in-out infinite",
              }}/>
              <span style={{
                fontSize: 12.5,
                color: "var(--text-secondary)",
                fontFamily: "var(--font-mono)",
                fontWeight: 400,
              }}>
                {upload.table_count} {upload.table_count === 1 ? "Tabelle" : "Tabellen"}
                {" · "}
                {upload.row_count.toLocaleString("de-DE")} Zeilen
              </span>
            </div>

            <button
              onClick={handleReset}
              style={{
                fontSize: 12.5,
                color: "var(--text-secondary)",
                background: "var(--bg-subtle)",
                border: "1px solid var(--border)",
                borderRadius: 999,
                padding: "5px 14px",
                cursor: "pointer",
                fontFamily: "var(--font-sans)",
                fontWeight: 500,
                transition: "all 0.15s ease",
                letterSpacing: "-0.01em",
              }}
              onMouseEnter={e => {
                const el = e.currentTarget;
                el.style.background = "var(--bg-hover)";
                el.style.borderColor = "var(--border-strong)";
                el.style.color = "var(--text-primary)";
              }}
              onMouseLeave={e => {
                const el = e.currentTarget;
                el.style.background = "var(--bg-subtle)";
                el.style.borderColor = "var(--border)";
                el.style.color = "var(--text-secondary)";
              }}
            >
              Neue Datei
            </button>
          </div>
        )}
      </header>

      {/* ── Main ── */}
      <main style={{
        flex: 1,
        maxWidth: upload ? 780 : "100%",
        width: "100%",
        margin: "0 auto",
        padding: upload ? "0 40px 140px" : 0,
        position: "relative",
      }}>
        {!upload ? (
          /* ── Landing ── */
          <div style={{ position: "relative", overflow: "hidden" }}>
            {/* Background dot grid + radial glow */}
            <div className="landing-bg" />

            <div style={{ position: "relative", zIndex: 1 }}>

              {/* ── Hero section ── */}
              <div style={{
                maxWidth: 780,
                margin: "0 auto",
                padding: "0 48px",
                paddingTop: "min(10vh, 88px)",
                paddingBottom: 56,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                textAlign: "center",
              }}>

                {/* Headline */}
                <h1 style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: "clamp(44px, 7vw, 72px)",
                  fontWeight: 800,
                  letterSpacing: "-0.05em",
                  lineHeight: 1.05,
                  color: "var(--text-primary)",
                  marginBottom: 22,
                  textAlign: "center",
                }}>
                  {[
                    { text: "Datei",      delay: 0.1,  dim: false },
                    { text: "hochladen.", delay: 0.18, dim: true  },
                    { text: " ",          delay: 0,    dim: false },
                    { text: "Fragen",     delay: 0.28, dim: false },
                    { text: "stellen.",   delay: 0.36, dim: true  },
                    { text: " ",          delay: 0,    dim: false },
                    { text: "Antworten", delay: 0.46, dim: false },
                    { text: "erhalten.", delay: 0.54, dim: true  },
                  ].map((w, i) =>
                    w.text === " " ? <br key={i}/> : (
                      <span
                        key={i}
                        className="word-animate"
                        style={{
                          display: "inline-block",
                          animationDelay: `${w.delay}s`,
                          color: w.dim ? "var(--text-tertiary)" : "var(--text-primary)",
                          marginRight: w.text.endsWith(".") ? "0.3em" : "0.22em",
                        }}
                      >
                        {w.text}
                      </span>
                    )
                  )}
                </h1>

                <p
                  className="word-animate"
                  style={{
                    color: "var(--text-secondary)",
                    fontSize: 15.5,
                    lineHeight: 1.6,
                    fontWeight: 400,
                    maxWidth: 400,
                    animationDelay: "0.55s",
                    marginBottom: 36,
                    letterSpacing: "-0.01em",
                  }}
                >
                  Stelle Fragen in natürlicher Sprache. DataChat schreibt
                  das SQL, führt es aus und erklärt die Ergebnisse in
                  Klartext, Tabellen und Charts.
                </p>

                {/* ── Capability marquee ── */}
                <div
                  className="word-animate"
                  style={{
                    animationDelay: "0.72s",
                    marginBottom: 44,
                    width: "100%",
                    overflow: "hidden",
                    maskImage: "linear-gradient(to right, transparent 0%, black 8%, black 92%, transparent 100%)",
                    WebkitMaskImage: "linear-gradient(to right, transparent 0%, black 8%, black 92%, transparent 100%)",
                  }}
                >
                  <div style={{
                    display: "flex",
                    gap: 8,
                    animation: "marquee 28s linear infinite",
                    width: "max-content",
                  }}>
                    {/* Two identical sets for seamless loop */}
                    {[...CAPABILITIES, ...CAPABILITIES].map((cap, i) => (
                      <span
                        key={i}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "6px 14px",
                          borderRadius: 999,
                          border: "1px solid var(--border)",
                          background: "var(--bg)",
                          fontSize: 13,
                          fontFamily: "var(--font-sans)",
                          fontWeight: 500,
                          color: "var(--text-secondary)",
                          letterSpacing: "-0.01em",
                          whiteSpace: "nowrap",
                          flexShrink: 0,
                          boxShadow: "var(--shadow-sm)",
                        }}
                      >
                        {cap.label}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Upload zone */}
                <div
                  className="word-animate"
                  style={{ animationDelay: "0.85s", width: "100%", display: "flex", justifyContent: "center" }}
                >
                  <UploadZone onUploaded={handleUploaded} />
                </div>

                {/* Format pills */}
                <div
                  className="word-animate"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    flexWrap: "wrap",
                    justifyContent: "center",
                    marginTop: 18,
                    animationDelay: "0.95s",
                  }}
                >
                  {[".csv", ".xlsx", ".xls", ".db", ".sqlite", ".sql"].map(ext => (
                    <span key={ext} className="pill" style={{ fontSize: 11 }}>{ext}</span>
                  ))}
                  <span style={{ fontSize: 12, color: "var(--text-tertiary)", marginLeft: 2 }}>max. 20 MB</span>
                </div>
              </div>

              {/* ── Divider ── */}
              <div style={{
                maxWidth: 780,
                margin: "0 auto",
                padding: "0 48px",
              }}>
                <div style={{
                  borderTop: "1px solid var(--border)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 12,
                  paddingTop: 0,
                  position: "relative",
                }}>
                  <span style={{
                    position: "absolute",
                    top: -10,
                    background: "var(--bg)",
                    padding: "0 14px",
                    fontSize: 11.5,
                    color: "var(--text-tertiary)",
                    fontFamily: "var(--font-mono)",
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                  }}>
                    So funktioniert's
                  </span>
                </div>
              </div>

              {/* ── Demo conversation ── */}
              <div style={{
                maxWidth: 780,
                margin: "0 auto",
                padding: "52px 48px 80px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 0,
              }}>
                <DemoConversation />
              </div>

            </div>
          </div>
        ) : (
          /* ── Chat view ── */
          <>
            <div style={{ paddingTop: 28 }} className="anim-fade-up">
              <SchemaInfo upload={upload} />
            </div>

            {history.length === 0 && !loading && (
              <div
                className="anim-fade-in"
                style={{
                  marginTop: 72,
                  textAlign: "center",
                }}
              >
                <div style={{
                  width: 44, height: 44,
                  background: "var(--bg-subtle)",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  margin: "0 auto 16px",
                  animation: "float 3s ease-in-out infinite",
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                </div>
                <p style={{
                  fontSize: 13.5,
                  color: "var(--text-tertiary)",
                  fontFamily: "var(--font-sans)",
                  fontWeight: 400,
                }}>
                  Stelle deine erste Frage
                </p>
              </div>
            )}

            {/* Loading skeleton */}
            {loading && (
              <div className="anim-fade-in" style={{ marginTop: 16 }}>
                <div style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: 16,
                  padding: "20px 24px",
                  boxShadow: "var(--shadow-sm)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
                    <div style={{
                      width: 20, height: 20, borderRadius: "50%",
                      border: "2px solid var(--border)",
                      borderTop: "2px solid var(--accent-blue)",
                      animation: "spin 0.75s linear infinite",
                      flexShrink: 0,
                    }}/>
                    <span style={{
                      fontSize: 13,
                      color: "var(--text-secondary)",
                      fontFamily: "var(--font-mono)",
                    }}>
                      Analysiere…
                    </span>
                  </div>
                  <div className="shimmer" style={{ height: 14, borderRadius: 6, marginBottom: 10, width: "72%" }}/>
                  <div className="shimmer" style={{ height: 14, borderRadius: 6, marginBottom: 10, width: "55%" }}/>
                  <div className="shimmer" style={{ height: 14, borderRadius: 6, width: "85%" }}/>
                </div>
              </div>
            )}

            {/* History */}
            {history.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}>
                {history.map((entry, i) => (
                  <div
                    key={i}
                    className="anim-fade-up"
                    style={{ animationDelay: `${Math.min(i * 0.04, 0.16)}s` }}
                  >
                    <AnswerCard result={entry.result} question={entry.question} />
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>

      {/* ── Sticky input ── */}
      {upload && (
        <div style={{
          position: "fixed",
          bottom: 0, left: 0, right: 0,
          zIndex: 40,
          background: "linear-gradient(to top, rgba(255,255,255,1) 50%, rgba(255,255,255,0))",
          padding: "28px 40px 24px",
        }}>
          <div style={{ maxWidth: 780, margin: "0 auto" }}>
            {error && (
              <div
                className="anim-slide-down"
                style={{
                  marginBottom: 10,
                  padding: "9px 14px",
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
            <ChatInput onSubmit={handleQuestion} loading={loading} />
          </div>
        </div>
      )}
    </div>
  );
}
