"use client";

export function Toggle({
  enabled,
  onChange,
  label,
}: {
  enabled: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        onClick={() => onChange(!enabled)}
        className={`relative inline-flex h-8 w-14 items-center rounded-full transition ${
          enabled ? "bg-acron-primary_accent" : "bg-neutral-border"
        }`}
      >
        <span
          className={`inline-block h-6 w-6 transform rounded-full bg-white transition ${
            enabled ? "translate-x-8" : "translate-x-1"
          }`}
        />
      </button>
      {label && <span className="text-sm text-neutral-dark-gray">{label}</span>}
    </div>
  );
}
