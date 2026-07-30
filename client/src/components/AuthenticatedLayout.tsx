import { type ReactNode } from "react";
import { Sidebar } from "@/components/Sidebar";
import { NestedPageLayoutContext } from "@/contexts/LayoutContext";

export function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh min-h-0 flex-col bg-background md:flex-row">
      <a
        href="#main-content"
        className="fixed left-3 top-3 z-[100] -translate-y-20 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-lg transition-transform focus:translate-y-0"
      >
        Ir para o conteúdo
      </a>
      <Sidebar />
      <div
        id="main-content"
        tabIndex={-1}
        className="flex min-h-0 min-w-0 flex-1 overflow-hidden outline-none"
      >
        <NestedPageLayoutContext.Provider value>
          {children}
        </NestedPageLayoutContext.Provider>
      </div>
    </div>
  );
}
