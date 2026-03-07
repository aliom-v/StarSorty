/**
 * Create a monotonic request tracker so stale async responses can be ignored.
 *
 * @returns {{
 *   begin: () => number,
 *   isCurrent: (requestId: number) => boolean,
 *   current: () => number,
 *   reset: () => void,
 * }}
 */
export function createRequestTracker() {
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
