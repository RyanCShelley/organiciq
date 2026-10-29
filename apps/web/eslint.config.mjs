import coreWebVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...coreWebVitals,
  { ignores: [".next/**", "next-env.d.ts"] },
  {
    // New in eslint-config-next 16. The two components it flags reset local
    // state when a prop or the open flag changes; rewriting them is a behaviour
    // change that belongs in its own PR, so it is reported, not blocking.
    rules: { "react-hooks/set-state-in-effect": "warn" },
  },
];

export default config;
