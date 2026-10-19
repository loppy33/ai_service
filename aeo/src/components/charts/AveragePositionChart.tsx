import { useMemo } from "react";
import { Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { TimeseriesPoint } from "../chat/types";

type Props = {
    data: TimeseriesPoint[];
    height?: number;
    midLine?: number;
};

export default function AveragePositionChart({ data, height = 130, midLine = 6 }: Props) {
    const rows = useMemo(
        () => (data || []).map((d) => ({ date: d.date, value: Math.max(1, Math.min(10, Number(d.value) || 10)) })),
        [data]
    );

    if (rows.length === 0) {
        return <div className="avgpos-chart" style={{ height }} />;
    }

    const values = rows.map((r) => r.value);
    const bestVal = Math.min(...values);
    const worstVal = Math.max(...values);
    const best = rows.find((r) => r.value === bestVal);
    const worst = rows.find((r) => r.value === worstVal);

    return (
        <div className="avgpos-chart">
            <ResponsiveContainer width="100%" height={height}>
                <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                    <ReferenceLine y={midLine} stroke="#ff7ab3" strokeDasharray="4 6" strokeOpacity={0.9} />
                    <XAxis dataKey="date" hide />
                    <YAxis hide domain={[10, 1]} reversed allowDecimals={false} />

                    <Line dataKey="value" stroke="#3b5bff" strokeWidth={2} dot={rows.length === 1} activeDot={false} />

                    {best && <ReferenceDot x={best.date} y={bestVal} r={4} fill="#000000" stroke="none" />}
                    {worst && (
                        <ReferenceDot
                            x={worst.date}
                            y={worstVal}
                            r={4}
                            fill="#ff4d79"
                            stroke="none"
                            style={{ filter: "drop-shadow(0 0 6px rgba(255,77,121,.6))" }}
                        />
                    )}
                </LineChart>
            </ResponsiveContainer>

            <div className="avgpos-legend">
                <div>Lowest position - {worstVal}</div>
                <div>Highest position - {bestVal}</div>
            </div>
        </div>
    );
}
