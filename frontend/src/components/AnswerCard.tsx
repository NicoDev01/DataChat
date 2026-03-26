import { useState } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, LabelList,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from "recharts";
import type { QueryResponse } from "../types";

// ── Palette ───────────────────────────────────────────────
// Notion-adjacent: charcoal first, then a considered set of saturated-but-not-loud colors
const PALETTE = [
  "#191919", "#0f7aff", "#0c8e5e", "#b45309", "#7c3aed",
  "#db2777", "#0891b2", "#4f7942"
];

// ── Helpers ───────────────────────────────────────────────
function AnnotatedAnswer({ text }: { text: string }) {
  const parts = text.split(
    /(\b(?:€\s?)?\d[\d.,]+(?:\s?(?:%|EUR|USD|Mio|Tsd|k|m))?\b)/g
  );
  return (
    <p style={{
      fontSize: 15,
      color: "var(--text-primary)",
      lineHeight: 1.75,
      fontWeight: 400,
      letterSpacing: "-0.01em",
      fontFamily: "var(--font-sans)",
    }}>
      {parts.map((part, i) => {
        const isNum = /^(€\s?)?\d[\d.,]+(\s?(%|EUR|USD|Mio|Tsd|k|m))?$/.test(part.trim());
        if (isNum) {
          return (
            <span key={i} style={{
              fontFamily: "var(--font-mono)",
              fontWeight: 700,
              fontSize: 14,
              color: "var(--text-primary)",
              background: "var(--bg-hover)",
              border: "1px solid var(--border)",
              borderRadius: 5,
              padding: "1px 6px",
              margin: "0 1px",
              letterSpacing: "-0.01em",
              display: "inline-block",
              lineHeight: 1.6,
            }}>
              {part}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

// ── Dotted background pattern (like evilcharts reference) ─
const DotPattern = ({ id }: { id: string }) => (
  <defs>
    <pattern id={id} x="0" y="0" width="10" height="10" patternUnits="userSpaceOnUse">
      <circle cx="2" cy="2" r="1" fill="var(--border-strong)" opacity="0.5" />
    </pattern>
  </defs>
);

// ── Custom Tooltip ─────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#fff",
      border: "1px solid var(--border-strong)",
      borderRadius: 10,
      padding: "10px 14px",
      fontFamily: "var(--font-sans)",
      fontSize: 12.5,
      boxShadow: "0 8px 24px rgba(0,0,0,0.11), 0 1px 4px rgba(0,0,0,0.06)",
      minWidth: 120,
    }}>
      {label !== undefined && label !== null && String(label) !== "" && (
        <p style={{
          color: "var(--text-tertiary)",
          marginBottom: 7,
          fontSize: 11,
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.03em",
          borderBottom: "1px dashed var(--border)",
          paddingBottom: 6,
        }}>
          {String(label).length > 22 ? String(label).slice(0, 21) + "…" : String(label)}
        </p>
      )}
      {payload.map((entry: any, i: number) => (
        <div key={i} style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: i < payload.length - 1 ? 5 : 0,
        }}>
          {/* Dashed indicator — matches evilcharts style */}
          <div style={{
            width: 16, height: 2,
            background: `repeating-linear-gradient(90deg, ${entry.color || "var(--text-primary)"} 0, ${entry.color || "var(--text-primary)"} 4px, transparent 4px, transparent 7px)`,
            flexShrink: 0,
          }}/>
          {entry.name && payload.length > 1 && (
            <span style={{ color: "var(--text-secondary)", fontSize: 12, flex: 1 }}>{entry.name}</span>
          )}
          <span style={{
            color: "var(--text-primary)",
            fontWeight: 700,
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            marginLeft: payload.length === 1 ? "auto" : 0,
          }}>
            {typeof entry.value === "number"
              ? entry.value.toLocaleString("de-DE")
              : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
};

// ── Chart Section ──────────────────────────────────────────
function ChartSection({ chart }: { chart: QueryResponse["chart"] }) {
  if (chart.type === "none" || !chart.data.length) return null;

  const isBar  = chart.type === "bar";
  const isLine = chart.type === "line";
  const isPie  = chart.type === "pie";

  const axisTickStyle = {
    fontSize: 11,
    fill: "var(--text-tertiary)" as string,
    fontFamily: "var(--font-mono)" as string,
  };

  const barCount    = chart.data.length;
  const maxLabelLen = Math.max(...chart.data.map(d => String(d[chart.x_key] ?? "").length));
  const rotateTicks = isBar && maxLabelLen > 8 && barCount > 5;
  const bottomMargin = rotateTicks ? 52 : 10;

  const chartH = isPie
    ? 270
    : Math.min(Math.max(210, barCount * 22), 290);

  const patternId = `dots-${chart.type}-${chart.y_keys[0]}`.replace(/[^a-z0-9-]/gi, "_");

  return (
    <div style={{ marginTop: 24, marginBottom: 2 }}>

      {/* Key label above chart */}
      {chart.y_keys.length === 1 && (
        <p style={{
          fontSize: 10.5,
          color: "var(--text-tertiary)",
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          marginBottom: 8,
        }}>
          {chart.y_keys[0]}
        </p>
      )}

      <ResponsiveContainer width="100%" height={chartH + bottomMargin}>

        {/* ── BAR ── */}
        {isBar ? (
          <BarChart
            data={chart.data}
            margin={{ top: 8, right: 4, left: 0, bottom: bottomMargin }}
            barCategoryGap="40%"
          >
            {/* Dotted background — evilcharts signature */}
            <rect x="0" y="0" width="100%" height="85%" fill={`url(#${patternId})`} />
            <DotPattern id={patternId} />

            <XAxis
              dataKey={chart.x_key}
              tick={rotateTicks
                ? { fontSize: 10, fill: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }
                : axisTickStyle
              }
              angle={rotateTicks ? -38 : 0}
              textAnchor={rotateTicks ? "end" : "middle"}
              tickLine={false}
              tickMargin={10}
              axisLine={false}
              interval={0}
              tickFormatter={(v) => {
                const s = String(v);
                if (!rotateTicks && s.length > 12) return s.slice(0, 11) + "…";
                if (rotateTicks && s.length > 16) return s.slice(0, 15) + "…";
                return s;
              }}
            />
            <YAxis
              tick={axisTickStyle}
              axisLine={false}
              tickLine={false}
              width={48}
              tickFormatter={(v) =>
                typeof v === "number" && Math.abs(v) >= 1000
                  ? `${(v / 1000).toFixed(0)}k`
                  : v
              }
            />
            <Tooltip
              cursor={false}
              content={<CustomTooltip />}
            />
            {chart.y_keys.length > 1 && (
              <Legend wrapperStyle={{
                fontFamily: "var(--font-sans)",
                fontSize: 12,
                color: "var(--text-secondary)",
                paddingTop: 10,
              }}/>
            )}
            {chart.y_keys.map((key, i) => (
              <Bar
                key={key}
                dataKey={key}
                fill={PALETTE[i % PALETTE.length]}
                radius={4}
                maxBarSize={52}
              />
            ))}
          </BarChart>

        /* ── LINE ── */
        ) : isLine ? (
          <LineChart
            data={chart.data}
            margin={{ top: 8, right: 12, left: 0, bottom: bottomMargin }}
          >
            {/* Horizontal grid only — evilcharts style */}
            <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="0" />

            <XAxis
              dataKey={chart.x_key}
              tick={axisTickStyle}
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={(v) => {
                const s = String(v);
                return s.length > 12 ? s.slice(0, 11) + "…" : s;
              }}
            />
            <YAxis
              tick={axisTickStyle}
              axisLine={false}
              tickLine={false}
              width={48}
              tickFormatter={(v) =>
                typeof v === "number" && Math.abs(v) >= 1000
                  ? `${(v / 1000).toFixed(0)}k`
                  : v
              }
            />
            <Tooltip cursor={false} content={<CustomTooltip />} />
            {chart.y_keys.length > 1 && (
              <Legend wrapperStyle={{
                fontFamily: "var(--font-sans)",
                fontSize: 12,
                color: "var(--text-secondary)",
                paddingTop: 10,
              }}/>
            )}
            {chart.y_keys.map((key, i) => (
              <Line
                key={key}
                type="linear"
                dataKey={key}
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={i === 0 ? 2 : 2}
                // Alternate: first series solid, second dashed — matches evilcharts multi-line
                strokeDasharray={i > 0 ? "4 4" : undefined}
                dot={false}
                activeDot={{
                  r: 5,
                  strokeWidth: 2,
                  stroke: "#fff",
                  fill: PALETTE[i % PALETTE.length],
                }}
              />
            ))}
          </LineChart>

        /* ── PIE ── */
        ) : (
          <PieChart margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <Tooltip content={<CustomTooltip />} />
            <Pie
              data={chart.data}
              dataKey={chart.y_keys[0]}
              nameKey={chart.x_key}
              cx="50%"
              cy="50%"
              innerRadius={44}
              outerRadius={90}
              cornerRadius={8}
              paddingAngle={4}
              strokeWidth={0}
            >
              {chart.data.map((_, i) => (
                <Cell
                  key={i}
                  fill={PALETTE[i % PALETTE.length]}
                />
              ))}
              {/* Value labels inside segments — evilcharts LabelList style */}
              <LabelList
                dataKey={chart.y_keys[0]}
                stroke="none"
                fontSize={11}
                fontWeight={600}
                fill="#fff"
                formatter={(v: number) =>
                  typeof v === "number" && v > 0
                    ? v >= 1000
                      ? `${(v / 1000).toFixed(0)}k`
                      : String(v)
                    : ""
                }
              />
            </Pie>
            <Legend
              wrapperStyle={{
                fontFamily: "var(--font-sans)",
                fontSize: 12,
                color: "var(--text-secondary)",
                paddingTop: 8,
              }}
            />
          </PieChart>
        )}

      </ResponsiveContainer>
    </div>
  );
}

// ── Table Section ──────────────────────────────────────────
function TableSection({ table }: { table: QueryResponse["table"] }) {
  const [open, setOpen] = useState(false);
  if (!table.columns.length) return null;

  const isNumericCol = table.columns.map((_, ci) =>
    table.rows.slice(0, 5).every(row => {
      const v = row[ci];
      return v !== null && v !== undefined && !isNaN(Number(v));
    })
  );

  return (
    <div style={{ marginTop: 16 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          fontSize: 12.5,
          fontWeight: 500,
          color: "var(--text-secondary)",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontFamily: "var(--font-sans)",
          padding: "3px 0",
          transition: "color 0.12s",
          letterSpacing: "-0.01em",
        }}
        onMouseEnter={e => (e.currentTarget.style.color = "var(--text-primary)")}
        onMouseLeave={e => (e.currentTarget.style.color = "var(--text-secondary)")}
      >
        <svg
          width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
          style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}
        >
          <polyline points="6 9 12 15 18 9"/>
        </svg>
        {open
          ? "Tabelle ausblenden"
          : `${table.rows.length} Zeile${table.rows.length !== 1 ? "n" : ""} anzeigen`}
      </button>

      {open && (
        <div
          className="anim-slide-down"
          style={{
            marginTop: 10,
            overflowX: "auto",
            borderRadius: 10,
            border: "1px solid var(--border)",
            maxHeight: 300,
            overflowY: "auto",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{
                background: "var(--bg-subtle)",
                position: "sticky",
                top: 0,
                borderBottom: "1px solid var(--border)",
              }}>
                {table.columns.map((col, ci) => (
                  <th key={col} style={{
                    padding: "9px 14px",
                    textAlign: isNumericCol[ci] ? "right" : "left",
                    color: "var(--text-tertiary)",
                    fontWeight: 500,
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                    whiteSpace: "nowrap",
                  }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, ri) => (
                <tr
                  key={ri}
                  className="table-row-hover"
                  style={{ borderTop: "1px solid var(--border)", transition: "background 0.1s" }}
                >
                  {row.map((val, ci) => (
                    <td key={ci} style={{
                      padding: "8px 14px",
                      color: "var(--text-primary)",
                      fontFamily: isNumericCol[ci] ? "var(--font-mono)" : "var(--font-sans)",
                      fontSize: 12.5,
                      textAlign: isNumericCol[ci] ? "right" : "left",
                      whiteSpace: "nowrap",
                      fontWeight: isNumericCol[ci] ? 600 : 400,
                    }}>
                      {val === null || val === undefined || val === ""
                        ? <span style={{ color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>—</span>
                        : String(val)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── SQL Viewer ─────────────────────────────────────────────
function SqlSection({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div style={{ marginTop: 12 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          fontSize: 12,
          fontWeight: 500,
          color: "var(--text-tertiary)",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
          padding: "3px 0",
          transition: "color 0.12s",
          letterSpacing: "0.01em",
        }}
        onMouseEnter={e => (e.currentTarget.style.color = "var(--text-secondary)")}
        onMouseLeave={e => (e.currentTarget.style.color = "var(--text-tertiary)")}
      >
        <svg
          width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
          style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 0.2s ease" }}
        >
          <polyline points="9 18 15 12 9 6"/>
        </svg>
        SQL
      </button>

      {open && (
        <div className="anim-slide-down" style={{ marginTop: 8, position: "relative" }}>
          <pre style={{
            background: "var(--bg-subtle)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "14px 48px 14px 16px",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            color: "var(--text-secondary)",
            overflowX: "auto",
            lineHeight: 1.8,
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}>
            {sql}
          </pre>
          <button
            onClick={copy}
            style={{
              position: "absolute",
              top: 9, right: 9,
              fontSize: 11,
              color: copied ? "var(--green)" : "var(--text-tertiary)",
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "3px 9px",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              transition: "color 0.15s",
              fontWeight: 500,
            }}
            onMouseEnter={e => { if (!copied) e.currentTarget.style.color = "var(--text-primary)"; }}
            onMouseLeave={e => { if (!copied) e.currentTarget.style.color = "var(--text-tertiary)"; }}
          >
            {copied ? "✓ kopiert" : "kopieren"}
          </button>
        </div>
      )}
    </div>
  );
}

// ── AnswerCard ─────────────────────────────────────────────
export function AnswerCard({ result, question }: { result: QueryResponse; question: string }) {
  const hasChart = result.chart?.type !== "none" && result.chart?.data?.length > 0;
  const hasTable = result.table?.columns?.length > 0;

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 16,
        overflow: "hidden",
        boxShadow: "var(--shadow-sm)",
        transition: "box-shadow 0.2s ease",
      }}
      onMouseEnter={e => (e.currentTarget.style.boxShadow = "var(--shadow-md)")}
      onMouseLeave={e => (e.currentTarget.style.boxShadow = "var(--shadow-sm)")}
    >
      {/* ── Question bar ── */}
      <div style={{
        padding: "13px 20px",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-subtle)",
        display: "flex",
        alignItems: "flex-start",
        gap: 11,
      }}>
        {/* Avatar */}
        <div style={{
          width: 24, height: 24, flexShrink: 0, marginTop: 1,
          background: "var(--text-primary)",
          borderRadius: 7,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        </div>

        {/* Question text — bold Notion style */}
        <span style={{
          fontSize: 14,
          color: "var(--text-primary)",
          lineHeight: 1.55,
          fontFamily: "var(--font-sans)",
          fontWeight: 700,
          letterSpacing: "-0.025em",
          paddingTop: 2,
        }}>
          {question}
        </span>
      </div>

      {/* ── Body ── */}
      <div style={{ padding: "20px 22px 18px" }}>
        {result.success ? (
          <>
            {/* Answer text with highlighted numbers */}
            <AnnotatedAnswer text={result.answer} />

            {/* Chart — no card, no grey bg, just inline */}
            {hasChart && <ChartSection chart={result.chart} />}

            {/* Divider + table + SQL */}
            {(hasTable || result.sql) && (
              <div style={{
                marginTop: 20,
                borderTop: "1px solid var(--border)",
                paddingTop: 14,
              }}>
                {hasTable && <TableSection table={result.table} />}
                <SqlSection sql={result.sql} />
              </div>
            )}
            {!hasTable && result.sql && (
              <div style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                <SqlSection sql={result.sql} />
              </div>
            )}
          </>
        ) : (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <div style={{
                width: 22, height: 22,
                background: "var(--red-bg)",
                border: "1px solid rgba(208,58,47,0.2)",
                borderRadius: 6,
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
              }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--red)" strokeWidth="2.5" strokeLinecap="round">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="12"/>
                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
              </div>
              <span style={{
                fontSize: 13,
                color: "var(--red)",
                fontFamily: "var(--font-sans)",
                fontWeight: 600,
                letterSpacing: "-0.01em",
              }}>
                Abfrage fehlgeschlagen
              </span>
            </div>
            <p style={{
              fontSize: 13,
              color: "var(--text-secondary)",
              fontFamily: "var(--font-mono)",
              lineHeight: 1.65,
              marginBottom: 14,
              padding: "10px 12px",
              background: "var(--bg-subtle)",
              borderRadius: 8,
              border: "1px solid var(--border)",
            }}>
              {result.error}
            </p>
            <SqlSection sql={result.sql} />
          </div>
        )}
      </div>
    </div>
  );
}
