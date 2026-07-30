import { createContext, useContext } from "react";

export const NestedPageLayoutContext = createContext(false);

export function useNestedPageLayout() {
  return useContext(NestedPageLayoutContext);
}
