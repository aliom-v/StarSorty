export function buildRepoDetailHref(fullName: string): string {
  const segments = String(fullName || "")
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment));

  if (segments.length === 0) {
    return "/repo";
  }

  return `/repo/${segments.join("/")}`;
}
