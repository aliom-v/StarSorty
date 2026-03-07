"use client";

import { memo } from "react";
import type { Messages, MessageValues } from "../lib/i18n";

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
  <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
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

  return (
    <article
      className={`group relative overflow-hidden rounded-[2.2rem] panel soft-elevated p-5 transition-all duration-500 hover:bg-surface/80 hover:shadow-premium card-3d-effect animate-fade-up dark:hover:bg-surface/85 md:p-7 stagger-${
        (index % 5) + 1
      }`}
    >
      <div className="card-sheen pointer-events-none absolute inset-x-0 top-0 h-28 rounded-t-[2.2rem] opacity-70" />
      <div className="pointer-events-none absolute -right-8 top-8 h-24 w-24 rounded-full bg-moss/8 opacity-60 blur-3xl dark:bg-moss/12" />

      <div className="flex flex-col justify-between gap-5 md:flex-row md:items-start md:gap-6">
        <div className="min-w-0 flex-1 space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold text-subtle">
            <span className="pill-muted max-w-full truncate">{repo.full_name}</span>
            {repo.category && (
              <span className="pill-accent">
                {repo.category}
                {repo.subcategory ? ` / ${repo.subcategory}` : ""}
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-start gap-3">
            <h3 className="min-w-0 flex-1 break-words font-display text-[1.28rem] font-black tracking-tight text-balance sm:text-[1.4rem] md:text-[1.6rem]">
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
            {repo.language && <span className="pill-accent shrink-0">{repo.language}</span>}
          </div>

          {displayDescription ? (
            <p className="line-clamp-3 text-sm font-medium leading-6 text-soft text-balance md:text-[15px] md:leading-7">
              {displayDescription}
            </p>
          ) : (
            <p className="text-sm font-medium italic text-subtle">{t("noDescription")}</p>
          )}

          <div className="flex flex-wrap items-center gap-4 text-[12px] font-semibold text-subtle md:gap-5">
            <div className="flex items-center gap-2 text-moss/80">
              <StarIcon />
              <span>{formatStars(repo.stargazers_count)}</span>
            </div>
            <div className="flex items-center gap-2">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>
                {t("updatedWithValue", {
                  date: formatDate(repo.updated_at, t("noData")),
                })}
              </span>
            </div>
            {repo.owner && <span className="text-ink/50 dark:text-ink/65">@{repo.owner}</span>}
          </div>
        </div>

        <div className="flex w-full shrink-0 items-center justify-between gap-3 sm:w-auto sm:justify-end md:flex-col md:items-end">
          <a
            href={`/repo/?full_name=${encodeURIComponent(repo.full_name)}`}
            className="flex flex-1 items-center justify-center rounded-full btn-ios-primary px-5 py-2.5 text-xs font-semibold tracking-[0.08em] sm:flex-none sm:px-6 sm:py-3"
          >
            {t("details")}
          </a>
          <a
            href={repo.html_url}
            target="_blank"
            rel="noreferrer"
            className="icon-button shrink-0"
            aria-label={t("viewOnGithub")}
          >
            <ExternalLinkIcon />
          </a>
        </div>
      </div>

      {(repo.tags?.length || repo.star_users?.length || repo.keywords?.length) && (
        <div className="mt-5 flex flex-wrap gap-2.5 border-t border-ink/5 pt-5 dark:border-white/5 md:mt-6 md:pt-6">
          {queryActive && repo.match_reasons && repo.match_reasons.length > 0 && (
            <span className="pill-copper px-3.5 py-2 text-[10px] tracking-[0.08em]">
              {t("matchedByWithValue", { value: repo.match_reasons.join(", ") })}
            </span>
          )}
          {repo.star_users && repo.star_users.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {repo.star_users.slice(0, 3).map((user) => (
                <span key={user} className="pill-muted px-3.5 py-2 text-[10px] text-ink/60">
                  @{user}
                </span>
              ))}
            </div>
          )}
          {repo.tags && repo.tags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {repo.tags.slice(0, 6).map((repoTag) => (
                <span key={repoTag} className="pill-accent px-3.5 py-2 text-[11px]">
                  #{repoTag}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
});

export default RepoCard;
