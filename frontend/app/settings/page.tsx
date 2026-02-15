"use client";

import { useState, useEffect } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Toggle } from "@/components/Toggle";
import { getBaseUrlClient } from "@/lib/api";

const API_KEY_STORAGE = "asahi_api_key";
const API_URL_STORAGE = "asahi_api_url";

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
      subtitle="Manage your ASAHI configuration"
    >
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setTab("general")}
          className={`px-4 py-2 rounded-button text-sm font-medium ${
            tab === "general"
              ? "bg-asahi-orange text-white"
              : "bg-neutral-light-gray text-neutral-dark-gray hover:bg-neutral-border"
          }`}
        >
          General
        </button>
        <button
          onClick={() => setTab("api")}
          className={`px-4 py-2 rounded-button text-sm font-medium ${
            tab === "api"
              ? "bg-asahi-orange text-white"
              : "bg-neutral-light-gray text-neutral-dark-gray hover:bg-neutral-border"
          }`}
        >
          API Keys
        </button>
      </div>

      {tab === "general" && (
        <Card>
          <h3 className="text-lg font-bold text-neutral-dark mb-4">General Settings</h3>
          <Input
            label="API Base URL"
            placeholder="https://your-asahi-api.railway.app"
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
          />
          <p className="text-sm text-neutral-dark-gray mb-4">
            Backend URL (e.g. Railway deployment). Leave blank to use NEXT_PUBLIC_API_URL.
          </p>
          <Button onClick={handleSave}>{saved ? "Saved" : "Save Changes"}</Button>
        </Card>
      )}

      {tab === "api" && (
        <Card>
          <h3 className="text-lg font-bold text-neutral-dark mb-4">API Key</h3>
          <p className="text-sm text-neutral-dark-gray mb-4">
            Your key is stored in this browser only. Set it below or get one via Sign Up.
          </p>
          <div className="flex gap-2 items-center mb-2">
            <input
              type={showKey ? "text" : "password"}
              value={displayKey}
              readOnly
              className="flex-1 px-4 py-2 border border-neutral-border rounded-card bg-neutral-light-gray text-neutral-dark-gray"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="text-sm text-asahi-orange hover:underline"
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
          />
          <Button onClick={handleSave}>{saved ? "Saved" : "Save"}</Button>
        </Card>
      )}
    </DashboardLayout>
  );
}
