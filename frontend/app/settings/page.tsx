"use client";

import { useState, useEffect } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

const API_KEY_STORAGE = "acron_api_key";
const API_URL_STORAGE = "acron_api_url";

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState("");
  const [apiUrl, setApiUrl] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);
  const [tab, setTab] = useState<"general" | "api">("general");

  useEffect(() => {
    if (typeof window === "undefined") return;
    setApiKey(localStorage.getItem(API_KEY_STORAGE) || "");
    setApiUrl(
      localStorage.getItem(API_URL_STORAGE) ||
      process.env.NEXT_PUBLIC_API_URL ||
      ""
    );
  }, []);

  function handleSave() {
    if (typeof window === "undefined") return;
    if (apiUrl.trim()) localStorage.setItem(API_URL_STORAGE, apiUrl.trim());
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
      subtitle="Manage your ACRON configuration"
    >
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setTab("general")}
          className={`px-4 py-2 rounded-button text-sm font-medium transition ${
            tab === "general"
              ? "bg-acron-primary_accent text-white"
              : "bg-neutral-light-gray text-neutral-dark-gray hover:bg-neutral-border hover:text-white"
          }`}
        >
          General
        </button>
        <button
          onClick={() => setTab("api")}
          className={`px-4 py-2 rounded-button text-sm font-medium transition ${
            tab === "api"
              ? "bg-acron-primary_accent text-white"
              : "bg-neutral-light-gray text-neutral-dark-gray hover:bg-neutral-border hover:text-white"
          }`}
        >
          API Keys
        </button>
      </div>

      {tab === "general" && (
        <Card>
          <h3 className="text-lg font-bold text-white mb-4">General Settings</h3>
          <Input
            label="API Base URL"
            placeholder="https://your-acron-api.railway.app"
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
            className="bg-neutral-dark border-neutral-border text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent"
          />
          <p className="text-sm text-neutral-dark-gray mb-4">
            Backend URL (e.g. Railway deployment). Leave blank to use NEXT_PUBLIC_API_URL.
          </p>
          <Button onClick={handleSave} variant="primary">{saved ? "Saved" : "Save Changes"}</Button>
        </Card>
      )}

      {tab === "api" && (
        <Card>
          <h3 className="text-lg font-bold text-white mb-4">API Key</h3>
          <p className="text-sm text-neutral-dark-gray mb-4">
            Your key is stored in this browser only. Set it below or get one via Sign Up.
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
      )}
    </DashboardLayout>
  );
}
