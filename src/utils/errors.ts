type ApiErrorShape = {
  message?: string;
  status?: number;
  response?: {
    data?: {
      detail?: string;
    };
  };
};

export function getErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message || fallback;
  if (error && typeof error === "object") {
    const shaped = error as ApiErrorShape;
    return shaped.response?.data?.detail || shaped.message || fallback;
  }
  return fallback;
}

export function isRateLimitError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const shaped = error as ApiErrorShape;
  const message = shaped.message ?? "";
  return shaped.status === 429 || message.includes("rate limit");
}

export function isNetworkError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const message = (error as ApiErrorShape).message ?? "";
  return message.includes("network") || message.includes("fetch");
}
