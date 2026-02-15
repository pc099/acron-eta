"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { deleteAccount } from "@/lib/api";

const API_KEY_STORAGE = "acron_api_key";

export default function ProfilePage() {
  const router = useRouter();
  const [hasKey, setHasKey] = useState(false);
  const [keyPrefix, setKeyPrefix] = useState("");
  const [deleteEmail, setDeleteEmail] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const key = localStorage.getItem(API_KEY_STORAGE);
    setHasKey(!!key);
    setKeyPrefix(key && key.length >= 12 ? `${key.slice(0, 12)}…` : "");
  }, []);

  async function handleDeleteAccount(e: React.FormEvent) {
    e.preventDefault();
    setDeleteError("");
    if (deleteConfirm !== "DELETE") {
      setDeleteError('Type DELETE in the confirmation box to proceed.');
      return;
    }
    if (!deleteEmail.trim() || !deletePassword) {
      setDeleteError("Enter your email and password.");
      return;
    }
    setDeleteLoading(true);
    try {
      await deleteAccount({ email: deleteEmail.trim(), password: deletePassword });
      if (typeof window !== "undefined") {
        localStorage.removeItem(API_KEY_STORAGE);
      }
      router.push("/login");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete account");
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <DashboardLayout
      title="Profile"
      subtitle="Your ACRON account"
    >
      <Card className="max-w-xl mb-6">
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

      <Card className="max-w-xl border-semantic-error/50">
        <h3 className="text-lg font-bold text-white mb-2">Delete account</h3>
        <p className="text-sm text-neutral-dark-gray mb-4">
          Permanently delete your account, API keys, and organization (if you are the only member). This cannot be undone.
        </p>
        <form onSubmit={handleDeleteAccount} className="space-y-4">
          <Input
            label="Your email"
            type="email"
            placeholder="you@example.com"
            value={deleteEmail}
            onChange={(e) => setDeleteEmail(e.target.value)}
            className="bg-neutral-dark border-neutral-border text-white"
          />
          <Input
            label="Your password"
            type="password"
            placeholder="••••••••"
            value={deletePassword}
            onChange={(e) => setDeletePassword(e.target.value)}
            className="bg-neutral-dark border-neutral-border text-white"
          />
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Type <span className="font-mono text-semantic-error">DELETE</span> to confirm
            </label>
            <input
              type="text"
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder="DELETE"
              className="w-full px-4 py-3 bg-neutral-dark border border-neutral-border rounded-card text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent outline-none"
            />
          </div>
          {deleteError && (
            <p className="text-sm text-semantic-error">{deleteError}</p>
          )}
          <Button
            type="submit"
            variant="primary"
            className="bg-semantic-error hover:bg-red-700"
            disabled={deleteLoading || deleteConfirm !== "DELETE"}
          >
            {deleteLoading ? "Deleting…" : "Delete my account"}
          </Button>
        </form>
      </Card>
    </DashboardLayout>
  );
}
