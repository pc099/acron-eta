"use client";

export function Card({
  children,
  highlight = false,
  className = "",
}: {
  children: React.ReactNode;
  highlight?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`p-6 rounded-card border transition ${
        highlight
          ? "border-acron-primary_accent bg-neutral-light-gray/50"
          : "border-neutral-border bg-neutral-dark hover:border-acron-primary_accent/50"
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function FeatureCard({
  icon,
  title,
  description,
  highlight,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  highlight?: boolean;
}) {
  return (
    <Card highlight={highlight}>
      <div
        className={`w-12 h-12 rounded-card flex items-center justify-center mb-4 text-xl ${
          highlight ? "bg-acron-primary_accent text-white" : "bg-neutral-light-gray text-acron-primary_accent"
        }`}
      >
        {icon}
      </div>
      <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
      <p className="text-neutral-dark-gray text-sm leading-relaxed">{description}</p>
    </Card>
  );
}
