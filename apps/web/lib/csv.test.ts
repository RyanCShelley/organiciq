// Run with: npx tsx apps/web/lib/csv.test.ts
import assert from "node:assert/strict";

import { csvCell } from "./csv";

// A third-party string that starts like a formula is neutralised.
assert.equal(csvCell('=HYPERLINK("x")'), `"'=HYPERLINK(""x"")"`);
assert.equal(csvCell("+1"), "'+1");
assert.equal(csvCell("-1 plumber"), "'-1 plumber");
assert.equal(csvCell("@sum"), "'@sum");
assert.equal(csvCell("\tcmd"), "'\tcmd");

// Numbers are not text: a negative stays a number.
assert.equal(csvCell(-3), "-3");
assert.equal(csvCell(0.5), "0.5");

// Ordinary quoting still works.
assert.equal(csvCell("a,b"), '"a,b"');
assert.equal(csvCell('say "hi"'), '"say ""hi"""');
assert.equal(csvCell(null), "");
assert.equal(csvCell("https://x.test/a-b"), "https://x.test/a-b");

console.log("csv: ok");
