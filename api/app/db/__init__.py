from .pool import init_db_pool, close_db_pool, get_connection  # noqa: F401
from .schema import init_db  # noqa: F401
from .sync import get_sync_status, update_sync_status  # noqa: F401
from .tasks import (  # noqa: F401
    create_task,
    create_task_if_available,
    update_task,
    get_task,
    get_active_task,
    reset_stale_tasks,
)
from .admin_sessions import (  # noqa: F401
    build_admin_session_expiry,
    create_admin_session,
    delete_admin_session,
    generate_admin_session_tokens,
    get_admin_session,
    purge_expired_admin_sessions,
)
from .repos import (  # noqa: F401
    upsert_repos,
    get_repo,
    prune_star_user,
    prune_users_not_in,
    record_readme_fetch,
    record_readme_fetches,
)
from .search import list_repos, iter_repos_for_export  # noqa: F401
from .classification import (  # noqa: F401
    update_classification,
    update_classifications_bulk,
    select_repos_for_classification,
    count_unclassified_repos,
    count_repos_for_classification,
    increment_classify_fail_count,
    reset_classify_fail_count,
    get_failed_repos,
)
from .override import update_override, list_override_history  # noqa: F401
from .stats import get_repo_stats  # noqa: F401
from .consistency import get_repo_consistency_report  # noqa: F401
from .runtime_guard import (  # noqa: F401
    AsyncSqliteRuntimeUnsupportedError,
    ensure_async_sqlite_runtime_supported,
    get_async_sqlite_runtime_issue,
)
from .user import (  # noqa: F401
    get_user_preferences,
    update_user_preferences,
    record_user_feedback_event,
    get_user_interest_profile,
    list_training_samples,
)
