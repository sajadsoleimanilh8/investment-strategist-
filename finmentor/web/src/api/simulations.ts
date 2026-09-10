import { api } from "./client";
import type { DecisionOut, ScenarioComparison, SimulationOut } from "./types";

/** All three simulators are the same endpoint with a different `kind`. */
export const runWhatIf = (userId: number, params: Record<string, number>) =>
  api.post<SimulationOut>("/api/simulations",
    { user_id: userId, kind: "what_if", params });

export const runDecision = (userId: number, price: number) =>
  api.post<DecisionOut>("/api/simulations",
    { user_id: userId, kind: "decision", params: { price } });

export const runTimeMachine = (userId: number, horizonMonths = 36) =>
  api.post<ScenarioComparison[]>("/api/simulations",
    { user_id: userId, kind: "time_machine", params: { horizon_months: horizonMonths } });
