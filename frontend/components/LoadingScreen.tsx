"use client";

import { useEffect, useState } from "react";

const INIT_DELAY_MS = 1200;

export default function LoadingScreen() {
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const t = setTimeout(() => setVisible(false), INIT_DELAY_MS);
    return () => clearTimeout(t);
  }, [mounted]);

  if (!mounted || !visible) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-acron-black flex flex-col items-center justify-center overflow-hidden">
      {/* Decorative arcs */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-0 w-full h-full border border-acron-primary_accent/20 rounded-full scale-150 -translate-x-1/4 -translate-y-1/4" style={{ clipPath: "ellipse(60% 40% at 30% 20%)" }} />
        <div className="absolute bottom-0 left-0 w-full h-full border border-acron-primary_accent/15 rounded-full scale-150 translate-x-1/4 translate-y-1/4" style={{ clipPath: "ellipse(50% 35% at 70% 80%)" }} />
      </div>
      <div className="relative flex flex-col items-center justify-center">
        {/* Rotating ACRON logo container */}
        <div className="relative w-28 h-28 mb-6 flex items-center justify-center">
          <div className="absolute inset-0 border-4 border-acron-primary_accent/25 border-t-acron-primary_accent rounded-full animate-spin" style={{ animationDuration: "2s" }} />
          <div className="absolute inset-3 border-2 border-white/20 rounded-full animate-spin" style={{ animationDuration: "3s", animationDirection: "reverse" }} />
          <div className="absolute inset-0 flex items-center justify-center bg-acron-black rounded-full">
            <img src="/logo.svg" alt="" className="w-12 h-12 object-contain drop-shadow-[0_0_8px_rgba(217,123,74,0.4)]" />
          </div>
        </div>
        <h2 className="text-white text-2xl font-bold tracking-[0.3em] mb-2 animate-pulse">ACRON</h2>
        <p className="text-neutral-dark-gray text-sm uppercase tracking-widest animate-pulse">Initializing system...</p>
      </div>
    </div>
  );
}
