import { cache } from "react";

import { apiFetch, type Client } from "@/lib/api";

/** The clients this person can see, fetched once per request. */
export const getClients = cache(() => apiFetch<Client[]>("/clients"));
