import { useMemo } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps } from "recharts";
import type { TimeseriesPoint } from "../chat/types";

type Props = {
    data: TimeseriesPoint[];
    height?: number;
};

function fmtDate(d: string) {
    return new Date(d).toLocaleString(undefined, { month: "short", day: "numeric" });
}

function ChartTooltip({ active, payload, label }: Partial<TooltipContentProps<number, string>>) {
    if (!active || !payload?.length) return null;
    const value = Number(payload[0]?.value ?? 0);
    return (
        <div
            style={{
                background: "rgba(255,255,255,0.95)",
                backdropFilter: "saturate(180%) blur(6px)",
                borderRadius: 10,
                boxShadow: "0 6px 20px rgba(0,0,0,.12)",
                padding: "8px 10px",
                fontSize: 12,
                color: "#222",
                border: "1px solid rgba(0,0,0,0.06)",
            }}
        >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{fmtDate(String(label))}</div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 999, background: "#58c25b" }} />
                <span style={{ opacity: 0.75 }}>Visibility</span>
                <strong style={{ marginLeft: "auto" }}>{value.toFixed(1)}%</strong>
            </div>
        </div>
    );
}

export default function VisibilityChart({ data, height = 130 }: Props) {
    const rows = useMemo(
        () => (data || []).map((d) => ({ date: d.date, value: Math.max(0, Math.min(100, Number(d.value) || 0)) })),
        [data]
    );

    if (rows.length === 0) {
        return <div className="vis-chart" style={{ height }} />;
    }

    const values = rows.map((r) => r.value);
    const yMin = Math.max(0, Math.min(...values) - 5);
    const yMax = Math.min(100, Math.max(...values) + 5);
    const showDots = rows.length === 1;

    return (
        <div className="vis-chart">
            <ResponsiveContainer width="100%" height={height}>
                <AreaChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                    <defs>
                        <linearGradient id="visGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#58c25b" stopOpacity={0.25} />
                            <stop offset="75%" stopColor="#58c25b" stopOpacity={0.06} />
                            <stop offset="100%" stopColor="#58c25b" stopOpacity={0} />
                        </linearGradient>
                    </defs>

                    <XAxis dataKey="date" hide tickFormatter={fmtDate} interval="preserveStartEnd" />
                    <YAxis hide domain={[yMin, yMax]} />

                    <Tooltip
                        content={ChartTooltip}
                        cursor={{ stroke: "rgba(0,0,0,0.25)", strokeWidth: 1 }}
                        position={{ y: 0 }}
                        wrapperStyle={{ outline: "none" }}
                    />

                    <Area
                        dataKey="value"
                        stroke="#58c25b"
                        strokeWidth={2}
                        fill="url(#visGradient)"
                        dot={showDots ? { r: 4, fill: "#58c25b", stroke: "#fff", strokeWidth: 2 } : false}
                        activeDot={{
                            r: 4,
                            fill: "#fff",
                            stroke: "#58c25b",
                            strokeWidth: 2,
                            style: { filter: "drop-shadow(0 0 10px rgba(88,194,91,.4))" },
                        }}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
}
