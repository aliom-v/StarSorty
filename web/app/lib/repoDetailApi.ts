import { getServerApiBaseUrl } from "./apiBase";
import type { RepoDetail } from "./repoDetailTypes";

export async function fetchRepoDetail(
  fullName: string
): Promise<RepoDetail | null> {
  if (!fullName) {
    return null;
  }

  const response = await fetch(
    `${getServerApiBaseUrl()}/repos/${encodeURIComponent(fullName)}`,
    {
      cache: "no-store",
    }
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`Repo fetch failed (${response.status})`);
  }

  return (await response.json()) as RepoDetail;
}
