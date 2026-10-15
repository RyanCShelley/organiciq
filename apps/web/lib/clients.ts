import { cache } from "react";

import { apiFetch, type Client } from "@/lib/api";

/**
 * The clients this person can see, fetched once per request.
 *
 * The app layout, the page under it, and the helpers that resolve a slug or an
 * id each asked the API for this same list — two or three round trips on every
 * navigation, with the full projection blob for every client in each. React's
 * `cache` shares one call across everything rendering the same request, and
 * forgets it when the request ends, so a save is never read back stale.
 */
export const getClients = cache(() => apiFetch<Client[]>("/clients"));
