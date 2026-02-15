"use client";

import { useState, useEffect } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

const API_KEY_STORAGE = "acron_api_key";

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setApiKey(localStorage.getItem(API_KEY_STORAGE) || "");
  }, []);

  function handleSave() {
    if (typeof window === "undefined") return;
    if (apiKey.trim()) localStorage.setItem(API_KEY_STORAGE, apiKey.trim());
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  const displayKey = apiKey
    ? showKey
      ? apiKey
      : `${apiKey.slice(0, 12)}${apiKey.length > 12 ? "…" : ""}`
    : "";

  return (
    <DashboardLayout
      title="Settings"
      subtitle="Manage your ACRON API key"
    >
      <Card>
          <h3 className="text-lg font-bold text-white mb-4">API Key</h3>
          <p className="text-sm text-neutral-dark-gray mb-4">
            Your key is stored in this browser only. Get one via Sign Up or Login; paste below to save.
          </p>
          <div className="flex gap-2 items-center mb-4">
            <input
              type={showKey ? "text" : "password"}
              value={displayKey}
              readOnly
              className="flex-1 px-4 py-2 border border-neutral-border rounded-card bg-neutral-dark text-white outline-none focus:border-acron-primary_accent"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="text-sm text-acron-primary_accent hover:text-white transition"
            >
              {showKey ? "Hide" : "Show"}
            </button>
          </div>
          <Input
            label="New API key (paste to save)"
            type="password"
            placeholder="Paste key and click Save"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="bg-neutral-dark border-neutral-border text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent"
          />
          <div className="mt-4">
            <Button onClick={handleSave} variant="primary">{saved ? "Saved" : "Save"}</Button>
          </div>
        </Card>
    </DashboardLayout>
  );
}
