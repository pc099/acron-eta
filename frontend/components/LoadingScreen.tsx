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
    <div className="fixed inset-0 z-[100] bg-black flex flex-col items-center justify-center">
      <div className="relative w-24 h-24 mb-6">
        {/* Outer rotating ring */}
        <div className="absolute inset-0 border-4 border-acron-primary_accent/30 border-t-acron-primary_accent rounded-full animate-spin"></div>
        
        {/* Inner static or counter-rotating element */}
        <div className="absolute inset-4 border-2 border-white/20 border-b-white rounded-full animate-spin direction-reverse duration-1000"></div>
        
        {/* Logo Icon in center */}
        <div className="absolute inset-0 flex items-center justify-center">
             <span className="text-white font-bold text-2xl">A</span>
        </div>
      </div>
      
      <div className="text-center">
        <h2 className="text-white text-xl font-bold tracking-wider mb-2">ACRON</h2>
        <p className="text-neutral-dark-gray text-sm animate-pulse">INITIALIZING SYSTEM...</p>
      </div>
    </div>
  );
}
