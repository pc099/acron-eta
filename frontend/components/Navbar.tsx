"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "./Button";

const API_KEY_STORAGE = "acron_api_key";

export function Navbar() {
  const router = useRouter();
  const [hasKey, setHasKey] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setHasKey(!!localStorage.getItem(API_KEY_STORAGE));
  }, []);

  function handleLogout() {
    if (typeof window !== "undefined") {
      localStorage.removeItem(API_KEY_STORAGE);
      setHasKey(false);
      router.push("/login");
    }
  }

  return (
    <nav className="fixed top-0 w-full bg-acron-black/90 backdrop-blur-md border-b border-neutral-border z-50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
        <Link href="/" className="flex items-center gap-2">
          <img src="/logo.svg" alt="ACRON" className="w-8 h-8 rounded object-contain" />
          <span className="font-bold text-xl text-white">ACRON</span>
        </Link>
        <div className="hidden md:flex items-center space-x-8">
          <Link href="/#features" className="text-neutral-dark-gray hover:text-white transition">
            Features
          </Link>
          <Link href="/#metrics" className="text-neutral-dark-gray hover:text-white transition">
            Metrics
          </Link>
          <Link href="/getting-started" className="text-neutral-dark-gray hover:text-white transition">
            Get Started
          </Link>
          <Link href="/#pricing" className="text-neutral-dark-gray hover:text-white transition">
            Pricing
          </Link>
        </div>
        <div className="flex gap-4">
          {hasKey ? (
            <>
              <Link href="/profile">
                <Button variant="ghost">Profile</Button>
              </Link>
              <Link href="/dashboard">
                <Button variant="ghost">Dashboard</Button>
              </Link>
              <Button variant="outline" onClick={handleLogout}>
                Log out
              </Button>
            </>
          ) : (
            <>
              <Link href="/login">
                <Button variant="ghost">Sign In</Button>
              </Link>
              <Link href="/signup">
                <Button variant="primary">Sign Up</Button>
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
