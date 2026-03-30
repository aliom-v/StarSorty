import assert from "node:assert/strict";
import test from "node:test";

import { buildRepoDetailHref } from "../app/lib/repoRoutes";

test("buildRepoDetailHref creates dynamic repo detail paths", () => {
  assert.equal(buildRepoDetailHref("owner/repo"), "/repo/owner/repo");
  assert.equal(
    buildRepoDetailHref("owner with space/repo+name"),
    "/repo/owner%20with%20space/repo%2Bname"
  );
  assert.equal(buildRepoDetailHref(""), "/repo");
});
