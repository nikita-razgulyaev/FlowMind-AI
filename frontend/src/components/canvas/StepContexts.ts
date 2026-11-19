import { createContext } from "react";
import type { StepIssue } from "../../utils/validateWorkflow";

/** Понятные названия шагов по id (для подписей на карточках). */
export const StepNamesContext = createContext<Record<string, string>>({});

/** Найденные при проверке проблемы по id шага. */
export const StepIssuesContext = createContext<Record<string, StepIssue[]>>({});
