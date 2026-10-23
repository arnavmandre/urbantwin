"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { Icon } from "@/components/ui/Icon";
import { cx } from "@/lib/cx";

/**
 * Right-hand slide-out for the scenario form.
 *
 * Always mounted: closing only slides it away and makes it `inert`, so the
 * form keeps its values and focus never lands on hidden controls. The form's
 * state is owned by the dashboard, not by this panel, so there is exactly one
 * copy of the scenario.
 *
 * It overlays the viewport instead of resizing it: the WebRTC video keeps its
 * size (and its connection) whether the drawer is open or closed.
 */
export function ScenarioDrawer({
  open,
  onClose,
  bottomInset,
  children,
}: {
  open: boolean;
  onClose: () => void;
  /** Keep the drawer above the results peek strip. */
  bottomInset: number;
  children: ReactNode;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) closeRef.current?.focus({ preventScroll: true });
  }, [open]);

  return (
    <aside
      id="scenario-drawer"
      aria-label="Scenario controls"
      aria-hidden={!open}
      inert={!open}
      // Full height on phones, where it is a full-screen sheet; above the
      // results peek strip from `sm` up, where both are visible side by side.
      style={{ ["--drawer-bottom" as string]: `${bottomInset}px` }}
      className={cx(
        "absolute bottom-0 right-0 top-0 z-30 flex w-full flex-col sm:bottom-[var(--drawer-bottom)] border-l border-hairline bg-surface-2 shadow-[var(--shadow-lift)] transition-transform duration-300 [transition-timing-function:var(--ease)] sm:w-[400px] sm:rounded-bl-[18px] lg:w-[420px]",
        open ? "translate-x-0" : "pointer-events-none translate-x-full",
      )}
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-hairline bg-surface px-4 py-2.5">
        <button
          type="button"
          onClick={onClose}
          className="rounded-[8px] px-2 py-1 text-[12px] font-semibold text-accent hover:bg-accent-soft sm:hidden"
        >
          &larr; Back to city
        </button>
        <p className="hidden text-[13px] font-semibold text-ink sm:block">
          Scenario
        </p>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Close scenario controls"
          className="ml-auto grid size-8 place-items-center rounded-[8px] text-ink-2 hover:bg-surface-2 hover:text-ink"
        >
          <Icon name="close" />
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain p-3 sm:p-4">
        {children}
      </div>
    </aside>
  );
}
