"use client";

import { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

const inputClass =
  "w-full px-4 py-3 bg-neutral-dark border border-neutral-border rounded-card text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent focus:ring-2 focus:ring-acron-primary_accent/20 outline-none transition";

export function Input({
  label,
  placeholder,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label?: string }) {
  return (
    <div className="mb-4">
      {label && (
        <label className="block text-sm font-medium text-white mb-2">{label}</label>
      )}
      <input placeholder={placeholder} className={`${inputClass} ${className}`} {...props} />
    </div>
  );
}

export function TextArea({
  label,
  placeholder,
  maxLength,
  value,
  onChange,
  rows = 5,
  className = "",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }) {
  return (
    <div className="mb-4">
      {label && (
        <label className="block text-sm font-medium text-neutral-dark mb-2">{label}</label>
      )}
      <textarea
        placeholder={placeholder}
        maxLength={maxLength}
        value={value}
        onChange={onChange}
        rows={rows}
        className={`${inputClass} resize-y ${className}`}
        {...props}
      />
      {typeof maxLength === "number" && (
        <p className="text-xs text-neutral-dark-gray mt-1">
          {(value as string)?.length ?? 0}/{maxLength}
        </p>
      )}
    </div>
  );
}
