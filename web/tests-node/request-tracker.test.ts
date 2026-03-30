import assert from "node:assert/strict";
import test from "node:test";

import {
  createAbortableRequestTracker,
  createRequestTracker,
  isAbortError,
} from "../app/lib/requestTracker";

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

test("createAbortableRequestTracker aborts the previous request on a new begin", () => {
  const tracker = createAbortableRequestTracker();
  const first = tracker.begin();
  const second = tracker.begin();

  assert.equal(first.requestId, 1);
  assert.equal(first.signal.aborted, true);
  assert.equal(second.requestId, 2);
  assert.equal(second.signal.aborted, false);
  assert.equal(tracker.isCurrent(first.requestId), false);
  assert.equal(tracker.isCurrent(second.requestId), true);
});

test("createAbortableRequestTracker reset aborts the active request", () => {
  const tracker = createAbortableRequestTracker();
  const active = tracker.begin();

  tracker.reset();

  assert.equal(active.signal.aborted, true);
  assert.equal(tracker.current(), 0);
  assert.equal(tracker.isCurrent(active.requestId), false);
});

test("isAbortError only matches AbortError-shaped failures", () => {
  const aborted = new Error("stopped");
  aborted.name = "AbortError";

  assert.equal(isAbortError(aborted), true);
  assert.equal(isAbortError(new Error("boom")), false);
  assert.equal(isAbortError("AbortError"), false);
});
