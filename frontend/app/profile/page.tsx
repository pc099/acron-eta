"use client";

import { useEffect, useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card } from "@/components/Card";

const API_KEY_STORAGE = "acron_api_key";

export default function ProfilePage() {
  const [hasKey, setHasKey] = useState(false);
  const [keyPrefix, setKeyPrefix] = useState("");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const key = localStorage.getItem(API_KEY_STORAGE);
    setHasKey(!!key);
    setKeyPrefix(key && key.length >= 12 ? `${key.slice(0, 12)}…` : "");
  }, []);

  return (
    <DashboardLayout
      title="Profile"
      subtitle="Your ACRON account"
    >
      <Card className="max-w-xl">
        <h3 className="text-lg font-bold text-white mb-4">Account</h3>
        <div className="space-y-4 text-neutral-dark-gray">
          <p>
            You are signed in. Your API key is stored in this browser.
            {keyPrefix && (
              <span className="block mt-2 font-mono text-sm text-white/80">
                Key prefix: {keyPrefix}
              </span>
            )}
          </p>
          {!hasKey && (
            <p className="text-semantic-warning">
              No API key in this browser. Sign in again or paste your key in Settings.
            </p>
          )}
        </div>
        <div className="mt-6 pt-4 border-t border-neutral-border">
          <p className="text-sm text-neutral-dark-gray">
            To update your API key or sign out, use Settings or Log out in the sidebar.
          </p>
        </div>
      </Card>
    </DashboardLayout>
  );
}
