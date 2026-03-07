export type TagMode = "or" | "and";
export type SortMode = "relevance" | "stars" | "updated";
export type ActionStatus = "success" | "error" | null;

export type Repo = {
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

export type RepoListResponse = {
  total?: number;
  items?: Repo[];
  has_more?: boolean;
  next_offset?: number | null;
  pagination_limited?: boolean;
};

export type Status = {
  last_sync_at?: string | null;
  last_result?: string | null;
  last_message?: string | null;
};

export type StatsItem = {
  name: string;
  count: number;
};

export type SubcategoryStatsItem = StatsItem & {
  category: string;
};

export type Stats = {
  total: number;
  unclassified: number;
  categories: StatsItem[];
  subcategories?: SubcategoryStatsItem[];
  tags: StatsItem[];
  users: StatsItem[];
};

export type BackgroundStatus = {
  running: boolean;
  started_at?: string | null;
  finished_at?: string | null;
  processed: number;
  failed: number;
  remaining: number;
  last_error?: string | null;
  batch_size: number;
  concurrency: number;
  task_id?: string | null;
};

export type TaskQueued = {
  task_id: string;
  status: string;
  message?: string | null;
};

export type TaskStatus = {
  task_id: string;
  status: string;
  task_type: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
  result?: Record<string, unknown> | null;
  retry_from_task_id?: string | null;
};

export type ClientSettings = {
  github_mode: string;
  classify_mode: string;
  auto_classify_after_sync: boolean;
};

export type TagGroupWithCounts = {
  id: string;
  name: string;
  tags: string[];
  tagCounts: StatsItem[];
};

export const PAGE_SIZE = 60;
