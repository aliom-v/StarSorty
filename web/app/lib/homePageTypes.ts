export type HomeTagMode = "or" | "and";

export type HomeSortMode = "relevance" | "stars" | "updated";

export type HomeActionStatus = "success" | "error" | null;

export type HomeRepo = {
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

export type HomeRepoListResponse = {
  total?: number;
  items?: HomeRepo[];
  has_more?: boolean;
  next_offset?: number | null;
  pagination_limited?: boolean;
};

export type HomeStatus = {
  last_sync_at?: string | null;
  last_result?: string | null;
  last_message?: string | null;
};

export type HomeStatsItem = {
  name: string;
  count: number;
};

export type HomeSubcategoryStatsItem = HomeStatsItem & {
  category: string;
};

export type HomeStats = {
  total: number;
  unclassified: number;
  categories: HomeStatsItem[];
  subcategories?: HomeSubcategoryStatsItem[];
  tags: HomeStatsItem[];
  users: HomeStatsItem[];
};

export type HomeBackgroundStatus = {
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

export type HomeTaskQueued = {
  task_id: string;
  status: string;
  message?: string | null;
};

export type HomeTaskStatus = {
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

export type HomeClientSettings = {
  github_mode: string;
  classify_mode: string;
  auto_classify_after_sync: boolean;
};

export type HomeTagGroupWithCounts = {
  id: string;
  name: string;
  tags: string[];
  tagCounts: HomeStatsItem[];
};
