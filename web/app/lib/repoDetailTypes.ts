export type RepoDetail = {
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
  ai_category?: string | null;
  ai_subcategory?: string | null;
  ai_confidence?: number | null;
  ai_tags?: string[];
  ai_provider?: string | null;
  ai_model?: string | null;
  ai_updated_at?: string | null;
  override_category?: string | null;
  override_subcategory?: string | null;
  override_tags?: string[];
  override_note?: string | null;
  readme_summary?: string | null;
  readme_fetched_at?: string | null;
  pushed_at?: string | null;
  updated_at?: string | null;
  starred_at?: string | null;
};

export type OverrideHistoryItem = {
  category?: string | null;
  subcategory?: string | null;
  tags?: string[];
  note?: string | null;
  updated_at?: string | null;
};
