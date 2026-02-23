from pydantic import BaseModel, ConfigDict, Field


class RssFeed(BaseModel):
    id: int
    name: str
    url: str
    is_active: bool
    created_at: str
    updated_at: str


class RssFeedCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    is_active: bool = True


class RssFeedUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    is_active: bool | None = None


class NewsItem(BaseModel):
    id: int
    feed_id: int
    guid: str
    title: str
    link: str
    published_at: str
    summary: str
    raw_json: str
    created_at: str
    feed_name: str = ""
