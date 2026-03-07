const POLLING_FAILURE_LIMIT = 3;
const POLLING_BASE_DELAY_MS = 8000;
const POLLING_MAX_DELAY_MS = 60000;

/**
 * @param {number} tick
 * @returns {boolean}
 */
export function shouldPollBackgroundStatus(tick) {
  return tick % 5 === 0;
}

/**
 * @param {number} failureCount
 * @param {boolean} hasActiveTask
 * @returns {number}
 */
export function getPollingDelayMs(failureCount, hasActiveTask) {
  if (!hasActiveTask) {
    return POLLING_BASE_DELAY_MS;
  }

  const safeFailureCount = Math.max(0, Number(failureCount) || 0);
  return Math.min(
    POLLING_MAX_DELAY_MS,
    POLLING_BASE_DELAY_MS * (2 ** safeFailureCount)
  );
}

/**
 * @param {{
 *   currentTaskId: string | null,
 *   expectedTaskId: string | null,
 *   activeRequestId: number,
 *   requestId: number,
 * }} state
 * @returns {boolean}
 */
function isTrackedPollCurrent(state) {
  return (
    state.currentTaskId === state.expectedTaskId &&
    state.activeRequestId === state.requestId
  );
}

/**
 * Evaluate a network or parse failure for tracked task polling.
 *
 * @param {{
 *   currentTaskId: string | null,
 *   expectedTaskId: string | null,
 *   activeRequestId: number,
 *   requestId: number,
 *   failureCount: number,
 * }} state
 * @returns {{
 *   ignore: boolean,
 *   nextFailureCount: number,
 *   pause: boolean,
 * }}
 */
export function evaluateTrackedPollFailure(state) {
  if (!isTrackedPollCurrent(state)) {
    return {
      ignore: true,
      nextFailureCount: state.failureCount,
      pause: false,
    };
  }

  const nextFailureCount = state.failureCount + 1;
  return {
    ignore: false,
    nextFailureCount,
    pause: nextFailureCount >= POLLING_FAILURE_LIMIT,
  };
}

/**
 * Evaluate a task polling HTTP response after the request is still current.
 *
 * @param {{
 *   currentTaskId: string | null,
 *   expectedTaskId: string | null,
 *   activeRequestId: number,
 *   requestId: number,
 *   status: number,
 *   failureCount: number,
 * }} state
 * @returns {{
 *   ignore: boolean,
 *   acceptResult: boolean,
 *   recoverMissingTask: boolean,
 *   nextFailureCount: number,
 *   pause: boolean,
 * }}
 */
export function evaluateTrackedPollResponse(state) {
  if (!isTrackedPollCurrent(state)) {
    return {
      ignore: true,
      acceptResult: false,
      recoverMissingTask: false,
      nextFailureCount: state.failureCount,
      pause: false,
    };
  }

  if (state.status === 404) {
    return {
      ignore: false,
      acceptResult: false,
      recoverMissingTask: true,
      nextFailureCount: 0,
      pause: false,
    };
  }

  if (state.status >= 500 || state.status === 429) {
    const nextFailureCount = state.failureCount + 1;
    return {
      ignore: false,
      acceptResult: false,
      recoverMissingTask: false,
      nextFailureCount,
      pause: nextFailureCount >= POLLING_FAILURE_LIMIT,
    };
  }

  if (state.status < 200 || state.status >= 300) {
    return {
      ignore: false,
      acceptResult: false,
      recoverMissingTask: false,
      nextFailureCount: state.failureCount,
      pause: false,
    };
  }

  return {
    ignore: false,
    acceptResult: true,
    recoverMissingTask: false,
    nextFailureCount: 0,
    pause: false,
  };
}
