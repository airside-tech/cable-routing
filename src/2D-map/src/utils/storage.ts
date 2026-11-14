import type { EditorData } from "../types";
import { importProjectJson } from "./json";

const STORAGE_KEY = "cable-routing-2d-map-v1";

export const saveDraft = (data: EditorData): void => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
};

export const loadDraft = (): EditorData | null => {
  const value = localStorage.getItem(STORAGE_KEY);
  if (!value) {
    return null;
  }

  try {
    return importProjectJson(value);
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
};

export const clearDraft = (): void => {
  localStorage.removeItem(STORAGE_KEY);
};
