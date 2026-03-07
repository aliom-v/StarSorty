import assert from "node:assert/strict";
import test from "node:test";

import { createRequestTracker } from "../app/lib/requestTracker.js";

test("createRequestTracker only keeps the latest request current", () => {
  const tracker = createRequestTracker();
  const first = tracker.begin();
  const second = tracker.begin();

  assert.equal(first, 1);
  assert.equal(second, 2);
  assert.equal(tracker.isCurrent(first), false);
  assert.equal(tracker.isCurrent(second), true);
});

test("createRequestTracker reset drops prior request ownership", () => {
  const tracker = createRequestTracker();
  const requestId = tracker.begin();

  tracker.reset();

  assert.equal(tracker.current(), 0);
  assert.equal(tracker.isCurrent(requestId), false);
});
