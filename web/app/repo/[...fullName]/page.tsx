import { notFound } from "next/navigation";
import RepoDetailClient from "../RepoDetailClient";
import { fetchRepoDetail } from "../../lib/repoDetailApi";

type RepoDetailDynamicPageProps = {
  params: Promise<{ fullName?: string[] }>;
};

export default async function RepoDetailDynamicPage({
  params,
}: RepoDetailDynamicPageProps) {
  const resolvedParams = await params;
  const fullName = (resolvedParams.fullName || [])
    .map((segment) => decodeURIComponent(segment))
    .join("/")
    .trim();

  if (!fullName) {
    notFound();
  }

  const repo = await fetchRepoDetail(fullName);
  if (!repo) {
    notFound();
  }

  return <RepoDetailClient initialFullName={fullName} initialRepo={repo} />;
}
