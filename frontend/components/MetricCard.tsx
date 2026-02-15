"use client";

import { Card } from "./Card";

export function MetricCard({
  value,
  label,
  unit = "",
  highlight = false,
}: {
  value: string | number;
  label: string;
  unit?: string;
  highlight?: boolean;
}) {
  return (
    <Card highlight={highlight}>
      <div className="text-center">
        <div
          className={`text-3xl md:text-4xl font-bold mb-2 ${highlight ? "text-acron-primary_accent" : "text-white"}`}
        >
          {value}
          {unit}
        </div>
        <div className="text-neutral-dark-gray text-sm font-medium">{label}</div>
      </div>
    </Card>
  );
}
