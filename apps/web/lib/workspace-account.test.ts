// Run with: npx tsx apps/web/lib/workspace-account.test.ts
import assert from "node:assert/strict";

import { isSmaWorkspaceAccount } from "./workspace-account";

// A Workspace account on either domain, with Google's `hd` claim.
assert.equal(isSmaWorkspaceAccount("a@smamarketing.com", "smamarketing.com"), true);
assert.equal(isSmaWorkspaceAccount("ryan@smamarketing.net", "smamarketing.net"), true);
// An alias on .net inside the .com Workspace carries the Workspace's domain.
assert.equal(isSmaWorkspaceAccount("a@smamarketing.net", "smamarketing.com"), true);
assert.equal(isSmaWorkspaceAccount("A@SMAMarketing.com", "SMAMarketing.com"), true);

// The case this exists for: a consumer Google account registered with an SMA
// address has no `hd`, and used to be let in on the address alone.
assert.equal(isSmaWorkspaceAccount("ex@smamarketing.net", undefined), false);
assert.equal(isSmaWorkspaceAccount("ex@smamarketing.net", null), false);
assert.equal(isSmaWorkspaceAccount("ex@smamarketing.net", ""), false);

// Another organisation's Workspace on our address, or ours on someone else's.
assert.equal(isSmaWorkspaceAccount("a@smamarketing.com", "evil.example"), false);
assert.equal(isSmaWorkspaceAccount("a@evil.example", "smamarketing.com"), false);
assert.equal(isSmaWorkspaceAccount("a@gmail.com", undefined), false);
assert.equal(isSmaWorkspaceAccount("", "smamarketing.com"), false);

// The way back in if a real staff account turns out not to carry `hd`.
process.env.SMA_ALLOW_ACCOUNTS_WITHOUT_HD = "true";
assert.equal(isSmaWorkspaceAccount("ryan@smamarketing.net", undefined), true);
assert.equal(isSmaWorkspaceAccount("a@gmail.com", undefined), false);

console.log("workspace-account: ok");
