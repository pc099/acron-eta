"use client";

import Link from "next/link";
import { Button } from "./Button";

export function Navbar() {
  return (
    <nav className="fixed top-0 w-full bg-neutral-white border-b border-neutral-border z-50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-asahi-orange flex items-center justify-center">
            <span className="text-white font-bold">A</span>
          </div>
          <span className="font-bold text-xl text-neutral-dark">ASAHI</span>
        </Link>
        <div className="hidden md:flex gap-8">
          <Link href="/#features" className="text-neutral-dark-gray hover:text-asahi-orange">
            Products
          </Link>
          <a
            href="/api-docs"
            className="text-neutral-dark-gray hover:text-asahi-orange"
          >
            Docs
          </a>
          <Link href="/#metrics" className="text-neutral-dark-gray hover:text-asahi-orange">
            Customers
          </Link>
          <Link href="/#pricing" className="text-neutral-dark-gray hover:text-asahi-orange">
            Pricing
          </Link>
        </div>
        <div className="flex gap-4">
          <Link href="/dashboard">
            <Button variant="ghost">Login</Button>
          </Link>
          <Link href="/signup">
            <Button variant="primary">Sign Up</Button>
          </Link>
        </div>
      </div>
    </nav>
  );
}
