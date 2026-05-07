"use client";

import Link from "next/link";
import { memo } from "react";
import type { Messages, MessageValues } from "../lib/i18n";
import { buildRepoDetailHref } from "../lib/repoRoutes";

type Repo = {
  full_name: string;
  name: string;
  owner: string;
  html_url: string;
  description?: string | null;
  language?: string | null;
  stargazers_count?: number | null;
  forks_count?: number | null;
  topics: string[];
  star_users?: string[];
  category?: string | null;
  subcategory?: string | null;
  tags?: string[];
  tag_ids?: string[];
  summary_zh?: string | null;
  keywords?: string[];
  search_score?: number | null;
  match_reasons?: string[];
  pushed_at?: string | null;
  updated_at?: string | null;
  starred_at?: string | null;
};

type RepoCardProps = {
  repo: Repo;
  index: number;
  queryActive: boolean;
  onRepoClick: (repo: Repo) => void;
  t: (key: keyof Messages, params?: MessageValues) => string;
};

const formatStars = (value?: number | null) => {
  const count = value ?? 0;
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(count);
};

const formatDate = (value?: string | null, fallback = "—") => {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleDateString();
};

const StarIcon = () => (
  <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 20 20">
    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
  </svg>
);

const ExternalLinkIcon = () => (
  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
  </svg>
);

const RepoCard = memo(function RepoCard({
  repo,
  index,
  queryActive,
  onRepoClick,
  t,
}: RepoCardProps) {
  const displayDescription = repo.summary_zh || repo.description;
  const classification = repo.category
    ? `${repo.category}${repo.subcategory ? ` / ${repo.subcategory}` : ""}`
    : null;

  return (
    <article
      className={`group animate-fade-up rounded-lg border border-ink/10 bg-surface p-4 shadow-soft transition hover:border-moss/25 hover:bg-moss/5 card-3d-effect stagger-${
        (index % 5) + 1
      }`}
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-xs font-semibold text-subtle">{repo.owner}</span>
            <span className="h-1 w-1 rounded-full bg-ink/20" />
            {repo.language && <span className="pill-muted">{repo.language}</span>}
            {classification && <span className="pill-accent">{classification}</span>}
            {queryActive && repo.match_reasons && repo.match_reasons.length > 0 && (
              <span className="pill-copper">
                {t("matchedByWithValue", { value: repo.match_reasons.join(", ") })}
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h3 className="min-w-0 break-words font-display text-lg font-semibold leading-tight text-ink sm:text-xl">
              <a
                href={repo.html_url}
                target="_blank"
                rel="noreferrer"
                className="transition-colors hover:text-moss"
                onClick={() => onRepoClick(repo)}
              >
                {repo.name}
              </a>
            </h3>
            <span className="min-w-0 truncate text-xs font-medium text-ink/40">
              {repo.full_name}
            </span>
          </div>

          {displayDescription ? (
            <p className="mt-2 line-clamp-2 max-w-5xl text-sm font-medium leading-6 text-soft">
              {displayDescription}
            </p>
          ) : (
            <p className="mt-2 text-sm font-medium italic text-subtle">{t("noDescription")}</p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs font-semibold text-subtle">
            <div className="flex items-center gap-1.5 text-moss">
              <StarIcon />
              <span>{formatStars(repo.stargazers_count)}</span>
            </div>
            <span>
              {t("updatedWithValue", {
                date: formatDate(repo.updated_at, t("noData")),
              })}
            </span>
            {repo.star_users && repo.star_users.length > 0 && (
              <span>
                {repo.star_users.slice(0, 3).map((user) => `@${user}`).join(", ")}
              </span>
            )}
          </div>

          {repo.tags && repo.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {repo.tags.slice(0, 7).map((repoTag) => (
                <span key={repoTag} className="pill-muted">
                  #{repoTag}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2 lg:justify-end">
          <Link
            href={buildRepoDetailHref(repo.full_name)}
            className="btn-ios-primary h-9 px-3.5 text-xs font-semibold"
          >
            {t("details")}
          </Link>
          <a
            href={repo.html_url}
            target="_blank"
            rel="noreferrer"
            className="icon-button"
            aria-label={t("viewOnGithub")}
            title={t("viewOnGithub")}
          >
            <ExternalLinkIcon />
          </a>
        </div>
      </div>
    </article>
  );
});

export default RepoCard;
