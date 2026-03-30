const POLLING_FAILURE_LIMIT = 3;
const POLLING_BASE_DELAY_MS = 8000;
const POLLING_MAX_DELAY_MS = 60000;

export function shouldPollBackgroundStatus(tick: number): boolean {
  return tick % 5 === 0;
}

export function getPollingDelayMs(
  failureCount: number,
  hasActiveTask: boolean
): number {
  if (!hasActiveTask) {
    return POLLING_BASE_DELAY_MS;
  }

  const safeFailureCount = Math.max(0, Number(failureCount) || 0);
  return Math.min(
    POLLING_MAX_DELAY_MS,
    POLLING_BASE_DELAY_MS * 2 ** safeFailureCount
  );
}

type TrackedPollState = {
  currentTaskId: string | null;
  expectedTaskId: string | null;
  activeRequestId: number;
  requestId: number;
  failureCount: number;
};

function isTrackedPollCurrent(state: TrackedPollState): boolean {
  return (
    state.currentTaskId === state.expectedTaskId &&
    state.activeRequestId === state.requestId
  );
}

export function evaluateTrackedPollFailure(state: TrackedPollState): {
  ignore: boolean;
  nextFailureCount: number;
  pause: boolean;
} {
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

export function evaluateTrackedPollResponse(
  state: TrackedPollState & { status: number }
): {
  ignore: boolean;
  acceptResult: boolean;
  recoverMissingTask: boolean;
  nextFailureCount: number;
  pause: boolean;
} {
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
