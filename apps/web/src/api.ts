export class ApiError extends Error {}

/** GET JSON from the API with human-readable errors. */
export async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("Can't reach the PGM Lens API. Start it with `make api`, or check that the server is running.");
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON; fall through to the generic message */
    }
    throw new ApiError(detail || `The API answered with an error (${response.status}).`);
  }
  return (await response.json()) as T;
}
