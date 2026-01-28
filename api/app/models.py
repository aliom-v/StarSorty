from pydantic import BaseModel, Field


class RepoBase(BaseModel):
    full_name: str
    name: str
    owner: str
    html_url: str
    description: str | None = None
    language: str | None = None
    stargazers_count: int | None = None
    forks_count: int | None = None
    topics: list[str] = Field(default_factory=list)
    pushed_at: str | None = None
    updated_at: str | None = None
    starred_at: str | None = None
    star_users: list[str] = Field(default_factory=list)
    category: str | None = None
    subcategory: str | None = None
    tags: list[str] = Field(default_factory=list)
    ai_category: str | None = None
    ai_subcategory: str | None = None
    ai_confidence: float | None = None
    ai_tags: list[str] = Field(default_factory=list)
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_updated_at: str | None = None
    override_category: str | None = None
    override_subcategory: str | None = None
    override_tags: list[str] = Field(default_factory=list)
    override_note: str | None = None
    readme_summary: str | None = None
    readme_fetched_at: str | None = None
    readme_last_attempt_at: str | None = None
    readme_failures: int | None = None
    readme_empty: bool | None = None
    summary_zh: str | None = None
    keywords: list[str] = Field(default_factory=list)
    ai_keywords: list[str] = Field(default_factory=list)
    override_summary_zh: str | None = None
    override_keywords: list[str] = Field(default_factory=list)


class ReadmeResult(BaseModel):
    success: bool
    summary: str | None = None
    error: str | None = None


class ClassificationResult(BaseModel):
    category: str
    subcategory: str
    tags: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reason: str | None = None
