export type RequestTracker = {
  begin: () => number;
  isCurrent: (requestId: number) => boolean;
  current: () => number;
  reset: () => void;
};

export type AbortableRequestTracker = {
  begin: () => { requestId: number; signal: AbortSignal };
  isCurrent: (requestId: number) => boolean;
  current: () => number;
  reset: () => void;
};

export function createRequestTracker(): RequestTracker {
  let latestRequestId = 0;

  return {
    begin() {
      latestRequestId += 1;
      return latestRequestId;
    },
    isCurrent(requestId) {
      return latestRequestId === requestId;
    },
    current() {
      return latestRequestId;
    },
    reset() {
      latestRequestId = 0;
    },
  };
}

export function createAbortableRequestTracker(): AbortableRequestTracker {
  const tracker = createRequestTracker();
  let controller: AbortController | null = null;

  return {
    begin() {
      if (controller) {
        controller.abort();
      }
      controller = new AbortController();
      return {
        requestId: tracker.begin(),
        signal: controller.signal,
      };
    },
    isCurrent(requestId) {
      return tracker.isCurrent(requestId);
    },
    current() {
      return tracker.current();
    },
    reset() {
      if (controller) {
        controller.abort();
        controller = null;
      }
      tracker.reset();
    },
  };
}

export function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== "object") {
    return false;
  }
  return (
    "name" in error &&
    error.name === "AbortError"
  );
}
