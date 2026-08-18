"use client";

import { useEffect, useState } from "react";
import RequireAuth from "../../lib/require-auth";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, PieChart, Pie, Cell,
} from "recharts";

const CATEGORY_COLORS = [
  "var(--stamp-teal)", "var(--stamp-ochre)", "var(--stamp-brick)",
  "var(--stamp-blue)", "var(--stamp-slate)", "var(--badge-purple)", "var(--stamp-paid)",
];

function formatMonth(month) {
  const [year, m] = month.split("-");
  const date = new Date(Number(year), Number(m) - 1);
  return date.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

// custom content instead of Tooltip's formatter prop -- avoids a recharts v3
// bug where formatter isn't reliably applied (recharts/recharts#6210)
function ChartTooltip({ active, payload, label, isCurrency = true }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div style={{
      background: "var(--paper-raised)", border: "1px solid var(--line)",
      borderRadius: 4, padding: "8px 12px", boxShadow: "var(--shadow-md)",
    }}>
      {label && (
        <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)", marginBottom: 4, fontWeight: 600 }}>
          {label}
        </div>
      )}
      {payload.map((entry, i) => (
        <div key={i} style={{ fontSize: "0.85rem", color: entry.color || "var(--ink)" }}>
          {entry.name || entry.dataKey}: {isCurrency ? `$${Number(entry.value).toFixed(2)}` : entry.value}
        </div>
      ))}
    </div>
  );
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function computeDateRange(year, month) {
  if (!year) return { date_from: undefined, date_to: undefined };
  if (!month) return { date_from: `${year}-01-01`, date_to: `${year}-12-31` };
  const mm = String(month).padStart(2, "0");
  const lastDay = new Date(Number(year), Number(month), 0).getDate();
  return { date_from: `${year}-${mm}-01`, date_to: `${year}-${mm}-${String(lastDay).padStart(2, "0")}` };
}

function AnalyticsPage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [selectedYear, setSelectedYear] = useState("");
  const [selectedMonth, setSelectedMonth] = useState("");
  const [availableYears, setAvailableYears] = useState([]);

  // Load once, unfiltered, purely to figure out which years actually have
  // data -- so the Year dropdown only offers years worth picking.
  useEffect(() => {
    api.analytics().then((result) => {
      const years = [...new Set(result.monthly_totals.map((m) => m.month.slice(0, 4)))].sort().reverse();
      setAvailableYears(years);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const { date_from, date_to } = computeDateRange(selectedYear, selectedMonth);
    api.analytics({ date_from, date_to }).then(setData).catch((err) => setError(err.message));
  }, [selectedYear, selectedMonth]);

  async function handleExport(format) {
    setExporting(true);
    setError("");
    try {
      const { date_from, date_to } = computeDateRange(selectedYear, selectedMonth);
      const url = format === "csv" ? api.exportCsvUrl({ date_from, date_to }) : api.exportPdfUrl({ date_from, date_to });
      await api.downloadFile(url, `expense_report.${format}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  }

  const isReviewer = user && (user.role === "reviewer" || user.role === "admin");

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Reporting</div>
          <h1>Analytics</h1>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className="btn btn-sm" onClick={() => handleExport("csv")} disabled={exporting}>
            Export CSV
          </button>
          <button className="btn btn-sm" onClick={() => handleExport("pdf")} disabled={exporting}>
            Export PDF
          </button>
        </div>
      </div>

      <div className="filter-bar" style={{ marginBottom: 20 }}>
        <div className="filter-field">
          <label className="filter-field-label">Year</label>
          <select
            value={selectedYear}
            onChange={(e) => {
              setSelectedYear(e.target.value);
              if (!e.target.value) setSelectedMonth("");
            }}
          >
            <option value="">All time</option>
            {availableYears.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label className="filter-field-label">Month</label>
          <select
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            disabled={!selectedYear}
          >
            <option value="">Whole year</option>
            {MONTH_NAMES.map((name, i) => (
              <option key={name} value={i + 1}>{name}</option>
            ))}
          </select>
        </div>
        {(selectedYear || selectedMonth) && (
          <div className="filter-field">
            <label className="filter-field-label">&nbsp;</label>
            <button className="btn btn-sm" onClick={() => { setSelectedYear(""); setSelectedMonth(""); }}>
              Clear
            </button>
          </div>
        )}
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      {!data ? (
        <p>Loading…</p>
      ) : (
        <>
          <div className="stat-grid" style={{ marginBottom: 24 }}>
            <div className="stat-tile">
              <div className="label">Average request</div>
              <div className="value">${data.average_request_amount.toFixed(2)}</div>
            </div>
            <div className="stat-tile">
              <div className="label">Avg. time to decision</div>
              <div className="value">
                {data.approval_time.avg_days != null ? `${data.approval_time.avg_days}d` : "—"}
              </div>
            </div>
            <div className="stat-tile">
              <div className="label">Median time to decision</div>
              <div className="value">
                {data.approval_time.median_days != null ? `${data.approval_time.median_days}d` : "—"}
              </div>
            </div>
            <div className="stat-tile">
              <div className="label">Decisions measured</div>
              <div className="value">{data.approval_time.count}</div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: 20 }}>
            <div className="eyebrow" style={{ marginBottom: 12 }}>Monthly spending</div>
            {data.monthly_totals.length === 0 ? (
              <p style={{ color: "var(--ink-soft)" }}>Not enough data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={data.monthly_totals.map((m) => ({ ...m, label: formatMonth(m.month) }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                  <XAxis dataKey="label" stroke="var(--ink-soft)" fontSize={12} />
                  <YAxis stroke="var(--ink-soft)" fontSize={12} tickFormatter={(v) => `$${v}`} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="total"
                    name="Total"
                    stroke="var(--stamp-teal)"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    activeDot={{ r: 7 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="card" style={{ marginBottom: 20 }}>
            <div className="eyebrow" style={{ marginBottom: 12 }}>Spending by category</div>
            {data.by_category.length === 0 ? (
              <p style={{ color: "var(--ink-soft)" }}>Not enough data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={data.by_category}
                    dataKey="total"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    label={(entry) => `${entry.category.replace(/_/g, " ")}: $${entry.total.toFixed(0)}`}
                  >
                    {data.by_category.map((entry, i) => (
                      <Cell key={entry.category} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>

          {isReviewer && (
            <>
              <div className="card" style={{ marginBottom: 20 }}>
                <div className="eyebrow" style={{ marginBottom: 12 }}>Spending by requester</div>
                {data.by_requester.length === 0 ? (
                  <p style={{ color: "var(--ink-soft)" }}>Not enough data yet.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={Math.max(200, data.by_requester.length * 45)}>
                    <BarChart data={data.by_requester} layout="vertical" margin={{ left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                      <XAxis type="number" stroke="var(--ink-soft)" fontSize={12} tickFormatter={(v) => `$${v}`} />
                      <YAxis type="category" dataKey="requester_name" stroke="var(--ink-soft)" fontSize={12} width={110} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="total" name="Total" fill="var(--stamp-blue)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>

              <div className="card" style={{ marginBottom: 20 }}>
                <div className="eyebrow" style={{ marginBottom: 12 }}>Reviewer workload</div>
                {data.reviewer_workload.length === 0 ? (
                  <p style={{ color: "var(--ink-soft)" }}>Not enough data yet.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={Math.max(200, data.reviewer_workload.length * 50)}>
                    <BarChart data={data.reviewer_workload} layout="vertical" margin={{ left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                      <XAxis type="number" stroke="var(--ink-soft)" fontSize={12} allowDecimals={false} />
                      <YAxis type="category" dataKey="reviewer_name" stroke="var(--ink-soft)" fontSize={12} width={110} />
                      <Tooltip content={<ChartTooltip isCurrency={false} />} />
                      <Legend />
                      <Bar dataKey="approved_count" name="Approved" stackId="a" fill="var(--stamp-teal)" />
                      <Bar dataKey="rejected_count" name="Rejected" stackId="a" fill="var(--stamp-brick)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}

export default function Page() {
  return (
    <RequireAuth roles={["requester", "reviewer", "admin"]}>
      <AnalyticsPage />
    </RequireAuth>
  );
}
