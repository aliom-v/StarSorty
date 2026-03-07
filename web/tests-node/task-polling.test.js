import assert from "node:assert/strict";
import test from "node:test";

import {
  evaluateTrackedPollFailure,
  evaluateTrackedPollResponse,
  getPollingDelayMs,
  shouldPollBackgroundStatus,
} from "../app/lib/taskPolling.js";

test("shouldPollBackgroundStatus only triggers every fifth tick", () => {
  assert.equal(shouldPollBackgroundStatus(4), false);
  assert.equal(shouldPollBackgroundStatus(5), true);
  assert.equal(shouldPollBackgroundStatus(10), true);
});

test("getPollingDelayMs keeps background status polling at the base interval", () => {
  assert.equal(getPollingDelayMs(0, false), 8000);
  assert.equal(getPollingDelayMs(3, false), 8000);
});

test("getPollingDelayMs exponentially backs off active task polling and caps it", () => {
  assert.equal(getPollingDelayMs(0, true), 8000);
  assert.equal(getPollingDelayMs(1, true), 16000);
  assert.equal(getPollingDelayMs(2, true), 32000);
  assert.equal(getPollingDelayMs(6, true), 60000);
});

test("evaluateTrackedPollFailure ignores stale request results", () => {
  const outcome = evaluateTrackedPollFailure({
    currentTaskId: "task-new",
    expectedTaskId: "task-old",
    activeRequestId: 3,
    requestId: 2,
    failureCount: 1,
  });

  assert.deepStrictEqual(outcome, {
    ignore: true,
    nextFailureCount: 1,
    pause: false,
  });
});

test("evaluateTrackedPollFailure pauses after the third consecutive failure", () => {
  const outcome = evaluateTrackedPollFailure({
    currentTaskId: "task-1",
    expectedTaskId: "task-1",
    activeRequestId: 4,
    requestId: 4,
    failureCount: 2,
  });

  assert.deepStrictEqual(outcome, {
    ignore: false,
    nextFailureCount: 3,
    pause: true,
  });
});

test("evaluateTrackedPollResponse triggers missing-task recovery on 404", () => {
  const outcome = evaluateTrackedPollResponse({
    currentTaskId: "task-1",
    expectedTaskId: "task-1",
    activeRequestId: 2,
    requestId: 2,
    status: 404,
    failureCount: 2,
  });

  assert.deepStrictEqual(outcome, {
    ignore: false,
    acceptResult: false,
    recoverMissingTask: true,
    nextFailureCount: 0,
    pause: false,
  });
});

test("evaluateTrackedPollResponse resets failures on successful current responses", () => {
  const outcome = evaluateTrackedPollResponse({
    currentTaskId: "task-1",
    expectedTaskId: "task-1",
    activeRequestId: 6,
    requestId: 6,
    status: 200,
    failureCount: 2,
  });

  assert.deepStrictEqual(outcome, {
    ignore: false,
    acceptResult: true,
    recoverMissingTask: false,
    nextFailureCount: 0,
    pause: false,
  });
});

test("evaluateTrackedPollResponse only counts retryable server failures", () => {
  const outcome = evaluateTrackedPollResponse({
    currentTaskId: "task-1",
    expectedTaskId: "task-1",
    activeRequestId: 5,
    requestId: 5,
    status: 500,
    failureCount: 1,
  });

  assert.deepStrictEqual(outcome, {
    ignore: false,
    acceptResult: false,
    recoverMissingTask: false,
    nextFailureCount: 2,
    pause: false,
  });
});
