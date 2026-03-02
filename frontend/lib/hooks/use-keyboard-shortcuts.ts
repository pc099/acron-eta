"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

/**
 * Linear-style keyboard shortcuts: press G then a key within 1s to navigate.
 *
 * G D → Dashboard
 * G G → Gateway
 * G C → Cache
 * G A → Analytics
 * G K → API Keys
 * G S → Settings
 */
export function useKeyboardShortcuts(orgSlug: string) {
  const router = useRouter();
  const pendingG = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Skip when focus is in an input, textarea, or contentEditable
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
      ) {
        return;
      }

      // Skip when modifier keys are held
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const key = e.key.toLowerCase();

      if (!pendingG.current) {
        if (key === "g") {
          pendingG.current = true;
          // Reset after 1 second
          if (timer.current) clearTimeout(timer.current);
          timer.current = setTimeout(() => {
            pendingG.current = false;
          }, 1000);
        }
        return;
      }

      // G was pressed, now handle the second key
      pendingG.current = false;
      if (timer.current) {
        clearTimeout(timer.current);
        timer.current = null;
      }

      const routes: Record<string, string> = {
        d: `/${orgSlug}/dashboard`,
        g: `/${orgSlug}/gateway`,
        c: `/${orgSlug}/cache`,
        a: `/${orgSlug}/analytics`,
        k: `/${orgSlug}/keys`,
        s: `/${orgSlug}/settings`,
      };

      const route = routes[key];
      if (route) {
        e.preventDefault();
        router.push(route);
      }
    };

    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      if (timer.current) clearTimeout(timer.current);
    };
  }, [orgSlug, router]);
}
