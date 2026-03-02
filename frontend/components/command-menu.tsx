"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  LayoutDashboard,
  Zap,
  Database,
  BarChart2,
  Key,
  Settings,
  Play,
  Plus,
  Search,
} from "lucide-react";

interface CommandMenuProps {
  orgSlug: string;
}

export function CommandMenu({ orgSlug }: CommandMenuProps) {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const navigate = (path: string) => {
    router.push(path);
    setOpen(false);
  };

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}
      <Command.Dialog
        open={open}
        onOpenChange={setOpen}
        label="Command Menu"
        className="fixed left-1/2 top-[20%] z-50 w-full max-w-lg -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-popover shadow-2xl"
      >
        <div className="flex items-center border-b border-border px-4">
          <Search className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
          <Command.Input
            placeholder="Type a command or search..."
            className="flex h-12 w-full bg-transparent py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
          <kbd className="ml-2 flex h-5 items-center gap-0.5 rounded border border-border bg-muted px-1.5 text-[10px] font-medium text-muted-foreground">
            ESC
          </kbd>
        </div>
        <Command.List className="max-h-80 overflow-y-auto p-2">
          <Command.Empty className="py-8 text-center text-sm text-muted-foreground">
            No results found.
          </Command.Empty>

          <Command.Group
            heading="Navigation"
            className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground"
          >
            <CommandItem
              icon={LayoutDashboard}
              label="Dashboard"
              shortcut="G D"
              onSelect={() => navigate(`/${orgSlug}/dashboard`)}
            />
            <CommandItem
              icon={Zap}
              label="Gateway"
              shortcut="G G"
              onSelect={() => navigate(`/${orgSlug}/gateway`)}
            />
            <CommandItem
              icon={Database}
              label="Cache"
              shortcut="G C"
              onSelect={() => navigate(`/${orgSlug}/cache`)}
            />
            <CommandItem
              icon={BarChart2}
              label="Analytics"
              shortcut="G A"
              onSelect={() => navigate(`/${orgSlug}/analytics`)}
            />
            <CommandItem
              icon={Key}
              label="API Keys"
              shortcut="G K"
              onSelect={() => navigate(`/${orgSlug}/keys`)}
            />
            <CommandItem
              icon={Settings}
              label="Settings"
              shortcut="G S"
              onSelect={() => navigate(`/${orgSlug}/settings`)}
            />
          </Command.Group>

          <Command.Separator className="my-1 h-px bg-border" />

          <Command.Group
            heading="Actions"
            className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground"
          >
            <CommandItem
              icon={Plus}
              label="Create API Key"
              onSelect={() => navigate(`/${orgSlug}/keys`)}
            />
            <CommandItem
              icon={Play}
              label="Open Playground"
              onSelect={() => navigate(`/${orgSlug}/gateway/playground`)}
            />
          </Command.Group>
        </Command.List>
      </Command.Dialog>
    </>
  );
}

function CommandItem({
  icon: Icon,
  label,
  shortcut,
  onSelect,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  shortcut?: string;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm text-foreground aria-selected:bg-muted"
    >
      <Icon className="h-4 w-4 text-muted-foreground" />
      <span className="flex-1">{label}</span>
      {shortcut && (
        <span className="flex items-center gap-1">
          {shortcut.split(" ").map((key, i) => (
            <kbd
              key={i}
              className="flex h-5 min-w-[20px] items-center justify-center rounded border border-border bg-muted px-1 text-[10px] font-medium text-muted-foreground"
            >
              {key}
            </kbd>
          ))}
        </span>
      )}
    </Command.Item>
  );
}
