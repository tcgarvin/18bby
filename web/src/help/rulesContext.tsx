import { createContext, useContext } from "react";
import type { Rules } from "../api";

const RulesContext = createContext<Rules | null>(null);

export const RulesProvider = RulesContext.Provider;

/** The live rule numbers. Only valid under a RulesProvider; App renders nothing until they load. */
export function useRules(): Rules {
  const rules = useContext(RulesContext);
  if (rules === null) throw new Error("useRules must be used under a RulesProvider");
  return rules;
}
