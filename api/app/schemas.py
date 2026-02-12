from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SyncResponse(BaseModel):
    status: str
    queued_at: str
    count: int


class StatusResponse(BaseModel):
    last_sync_at: str | None
    last_result: str | None
    last_message: str | None


class TaskQueuedResponse(BaseModel):
    task_id: str
    status: str
    message: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    task_type: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    message: str | None
    result: dict | None
    cursor_full_name: str | None = None
    retry_from_task_id: str | None = None


class RepoOut(BaseModel):
    full_name: str
    name: str
    owner: str
    html_url: str
    description: str | None
    language: str | None
    stargazers_count: int | None
    forks_count: int | None
    topics: List[str]
    star_users: List[str]
    category: str | None
    subcategory: str | None
    tags: List[str]
    tag_ids: List[str] = Field(default_factory=list)
    ai_category: str | None
    ai_subcategory: str | None
    ai_confidence: float | None
    ai_tags: List[str]
    ai_tag_ids: List[str] = Field(default_factory=list)
    ai_keywords: List[str]
    ai_provider: str | None
    ai_model: str | None
    ai_reason: str | None = None
    ai_decision_source: str | None = None
    ai_rule_candidates: List[Dict[str, object]] = Field(default_factory=list)
    ai_updated_at: str | None
    override_category: str | None
    override_subcategory: str | None
    override_tags: List[str]
    override_tag_ids: List[str] = Field(default_factory=list)
    override_note: str | None
    override_summary_zh: str | None
    override_keywords: List[str]
    readme_summary: str | None
    readme_fetched_at: str | None
    pushed_at: str | None
    updated_at: str | None
    starred_at: str | None
    summary_zh: str | None
    keywords: List[str]
    search_score: float | None = None
    match_reasons: List[str] = Field(default_factory=list)


class RepoListResponse(BaseModel):
    total: int
    items: List[RepoOut]


class OverrideRequest(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = None
    tag_ids: Optional[List[str]] = None
    note: Optional[str] = None


class OverrideResponse(BaseModel):
    updated: bool


class OverrideHistoryItem(BaseModel):
    category: str | None
    subcategory: str | None
    tags: List[str]
    note: str | None
    updated_at: str | None


class OverrideHistoryResponse(BaseModel):
    items: List[OverrideHistoryItem]


class ClassifyRequest(BaseModel):
    limit: int = Field(default=20, ge=0)
    force: bool = False
    include_readme: bool = True
    preference_user: Optional[str] = "global"


class ClassifyResponse(BaseModel):
    total: int
    classified: int
    failed: int
    remaining_unclassified: int


class BackgroundClassifyRequest(ClassifyRequest):
    concurrency: Optional[int] = Field(default=None, ge=1)
    cursor_full_name: Optional[str] = None


class BackgroundClassifyResponse(BaseModel):
    started: bool
    running: bool
    message: str
    task_id: str | None = None


class BackgroundClassifyStatusResponse(BaseModel):
    running: bool
    started_at: str | None
    finished_at: str | None
    processed: int
    failed: int
    remaining: int
    last_error: str | None
    batch_size: int
    concurrency: int
    task_id: str | None = None


class UserPreferencesRequest(BaseModel):
    tag_mapping: Optional[Dict[str, str]] = None
    rule_priority: Optional[Dict[str, int]] = None


class UserPreferencesResponse(BaseModel):
    user_id: str
    tag_mapping: Dict[str, str]
    rule_priority: Dict[str, int]
    updated_at: str | None = None


class SearchFeedbackRequest(BaseModel):
    user_id: str = "global"
    query: str
    results_count: int = Field(default=0, ge=0)
    selected_tags: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    subcategory: Optional[str] = None


class ClickFeedbackRequest(BaseModel):
    user_id: str = "global"
    full_name: str
    query: Optional[str] = None


class FeedbackResponse(BaseModel):
    ok: bool


class InterestTopicItem(BaseModel):
    topic: str
    score: float


class InterestProfileResponse(BaseModel):
    user_id: str
    topic_scores: Dict[str, float]
    top_topics: List[InterestTopicItem]
    updated_at: str | None = None


class TrainingSampleItem(BaseModel):
    id: int
    user_id: str | None = None
    full_name: str
    before_category: str | None = None
    before_subcategory: str | None = None
    before_tag_ids: List[str] = Field(default_factory=list)
    after_category: str | None = None
    after_subcategory: str | None = None
    after_tag_ids: List[str] = Field(default_factory=list)
    note: str | None = None
    source: str | None = None
    created_at: str


class TrainingSamplesResponse(BaseModel):
    items: List[TrainingSampleItem]
    total: int


class FewShotItem(BaseModel):
    input: Dict[str, object]
    output: Dict[str, object]
    note: Optional[str] = None


class FewShotResponse(BaseModel):
    items: List[FewShotItem]
    total: int


class ReadmeResponse(BaseModel):
    updated: bool
    summary: str


class TaxonomyCategory(BaseModel):
    name: str
    subcategories: List[str] = Field(default_factory=list)


class TaxonomyTagDef(BaseModel):
    id: str
    zh: str
    group: str


class TaxonomyResponse(BaseModel):
    categories: List[TaxonomyCategory]
    tags: List[str]
    tag_defs: List[TaxonomyTagDef] = Field(default_factory=list)


class SettingsResponse(BaseModel):
    github_username: str
    github_target_username: str
    github_usernames: str
    github_include_self: bool
    github_mode: str
    classify_mode: str
    auto_classify_after_sync: bool
    rules_json: str
    sync_cron: str
    sync_timeout: int
    github_token_set: bool
    ai_api_key_set: bool


class SettingsRequest(BaseModel):
    github_username: Optional[str] = None
    github_target_username: Optional[str] = None
    github_usernames: Optional[str] = None
    github_include_self: Optional[bool] = None
    github_mode: Optional[str] = None
    classify_mode: Optional[str] = None
    auto_classify_after_sync: Optional[bool] = None
    rules_json: Optional[str] = None
    sync_cron: Optional[str] = None
    sync_timeout: Optional[int] = Field(default=None, ge=1, le=3600)


class ClientSettingsResponse(BaseModel):
    github_mode: str
    classify_mode: str
    auto_classify_after_sync: bool


class StatsItem(BaseModel):
    name: str
    count: int


class SubcategoryStatsItem(StatsItem):
    category: str


class StatsResponse(BaseModel):
    total: int
    unclassified: int
    categories: List[StatsItem]
    subcategories: List[SubcategoryStatsItem]
    tags: List[StatsItem]
    users: List[StatsItem]


class FailedRepoItem(BaseModel):
    full_name: str
    name: str
    owner: str
    description: Optional[str] = None
    language: Optional[str] = None
    classify_fail_count: int


class FailedReposResponse(BaseModel):
    items: List[FailedRepoItem]
    total: int


class ResetFailedResponse(BaseModel):
    reset_count: int
