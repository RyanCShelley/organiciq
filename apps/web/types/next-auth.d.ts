// No custom fields on the session or the token. The API credential is signed
// per request on the server (lib/auth.ts) and must never appear on an object
// the browser can read.
import "next-auth";
import "next-auth/jwt";
