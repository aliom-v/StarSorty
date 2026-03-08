"use client";

import type { Messages, MessageValues } from "../lib/i18n";
import type {
  HomeStatsItem,
  HomeTagGroupWithCounts,
  HomeTagMode,
} from "../lib/homePageTypes";

type SidebarProps = {
  t: (key: keyof Messages, params?: MessageValues) => string;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  selectedTags: string[];
  handleTagToggle: (tag: string) => void;
  setSelectedTags: (tags: string[]) => void;
  tagMode: HomeTagMode;
  setTagMode: (mode: HomeTagMode) => void;
  tagGroups: HomeTagGroupWithCounts[];
  groupMode: boolean;
  sourceUser: string | null;
  setSourceUser: (user: string | null) => void;
  userCounts: HomeStatsItem[];
  overallTotal: number;
  unclassifiedCount: number;
};

const Sidebar = ({
  t,
  sidebarOpen,
  setSidebarOpen,
  selectedTags,
  handleTagToggle,
  setSelectedTags,
  tagMode,
  setTagMode,
  tagGroups,
  groupMode,
  sourceUser,
  setSourceUser,
  userCounts,
  overallTotal,
  unclassifiedCount,
}: SidebarProps) => {
  return (
    <div className="flex h-full flex-col p-5 lg:p-8">
      <div className="mb-8 flex flex-shrink-0 items-center justify-between">
        <h2 className="section-title text-xl font-black md:text-2xl">
          {t("tagCloud")}
        </h2>
        {sidebarOpen && (
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="icon-button md:hidden"
            aria-label={t("back")}
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="custom-scrollbar -mr-4 flex flex-1 flex-col gap-10 overflow-y-auto pr-4">
        {selectedTags.length > 0 && (
          <div className="animate-fade-in space-y-4">
            <div className="flex items-center justify-between px-1">
              <p className="section-kicker">
                {t("selectedTags")}
              </p>
              <button
                type="button"
                className="text-[10px] font-black uppercase tracking-[0.12em] text-copper transition-all hover:text-copper/60"
                onClick={() => setSelectedTags([])}
              >
                {t("clearTags")}
              </button>
            </div>
            <div className="flex flex-wrap gap-2.5">
              {selectedTags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  className="group flex items-center gap-2 rounded-full btn-ios-primary px-4 py-2 text-[11px] font-semibold tracking-[0.04em] shadow-soft active:scale-95"
                  onClick={() => handleTagToggle(tag)}
                >
                  {tag}
                  <span className="opacity-40 group-hover:opacity-100 transition-opacity">×</span>
                </button>
              ))}
            </div>
            <div className="tag-cloud-shell flex w-fit items-center gap-1 rounded-full border border-ink/5 bg-ink/[0.03] p-1 shadow-inner">
              <button
                type="button"
                className={`rounded-full px-4 py-1.5 text-[10px] font-black transition-all ${
                  tagMode === "or" ? "bg-surface text-ink shadow-sm" : "text-ink/40"
                }`}
                onClick={() => setTagMode("or")}
              >
                {t("any")}
              </button>
              <button
                type="button"
                className={`rounded-full px-4 py-1.5 text-[10px] font-black transition-all ${
                  tagMode === "and" ? "bg-surface text-ink shadow-sm" : "text-ink/40"
                }`}
                onClick={() => setTagMode("and")}
              >
                {t("all")}
              </button>
            </div>
          </div>
        )}

        <div className="space-y-8">
          {tagGroups.map((group) => (
            <div key={group.id} className="space-y-4">
              <h3 className="section-kicker px-1">
                {group.name}
              </h3>
              <div className="flex flex-wrap gap-2.5">
                {group.tagCounts.map((tagItem) => (
                  <button
                    key={tagItem.name}
                    type="button"
                    className={`tag-cloud-chip rounded-2xl px-3.5 py-2 text-[11px] font-semibold transition-all duration-300 ${
                      selectedTags.includes(tagItem.name)
                        ? "btn-ios-moss scale-[1.02] text-white"
                        : "btn-ios-secondary text-ink/70 hover:border-moss/40 hover:text-moss"
                    }`}
                    onClick={() => handleTagToggle(tagItem.name)}
                  >
                    {tagItem.name}
                    <span className={`ml-2 text-[10px] font-black opacity-30 ${selectedTags.includes(tagItem.name) ? "text-white opacity-60" : ""}`}>
                      {tagItem.count}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {groupMode && (
          <div className="space-y-4">
            <h3 className="section-kicker px-1">
              {t("users")}
            </h3>
            <div className="tag-cloud-shell overflow-hidden rounded-[2rem] border border-ink/5 bg-ink/[0.03] shadow-inner">
              <button
                className={`flex w-full items-center justify-between px-5 py-4 text-sm font-semibold transition-all border-b border-ink/5 active:bg-ink/5 ${
                  sourceUser === null
                    ? "bg-surface text-ink shadow-sm"
                    : "text-ink/60 hover:bg-surface/40"
                }`}
                onClick={() => setSourceUser(null)}
              >
                <span>{t("all")}</span>
                <span className="text-[10px] font-black opacity-30">{overallTotal}</span>
              </button>
              {userCounts.map((user, idx) => (
                <button
                  key={user.name}
                  className={`flex w-full items-center justify-between px-5 py-4 text-sm font-semibold transition-all active:bg-ink/5 ${
                    idx !== userCounts.length - 1 ? "border-b border-ink/5" : ""
                  } ${
                    sourceUser === user.name
                      ? "bg-surface text-ink shadow-sm"
                      : "text-ink/60 hover:bg-surface/40"
                  }`}
                  onClick={() => setSourceUser(user.name)}
                >
                  <span>@{user.name}</span>
                  <span className="text-[10px] font-black opacity-30">{user.count}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-auto space-y-4 border-t border-ink/5 pt-8">
          <div className="grid grid-cols-1 gap-4">
            <div className="panel-muted flex items-center justify-between p-5">
              <p className="section-kicker">{t("total")}</p>
              <p className="text-3xl font-display font-black text-ink leading-none">{overallTotal}</p>
            </div>
            <div className="panel-muted flex items-center justify-between border-moss/10 bg-moss/5 p-5">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-moss/50">{t("unclassified")}</p>
              <p className="text-3xl font-display font-black text-moss leading-none">{unclassifiedCount}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
