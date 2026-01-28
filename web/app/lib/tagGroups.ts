export interface TagGroup {
  id: string;
  name: string;
  tags: string[];
}

export const TAG_GROUPS: TagGroup[] = [
  { id: "project_type", name: "项目类型", tags: ["工具", "框架", "库", "SDK", "插件", "模板", "脚手架", "资源合集", "教程"] },
  { id: "runtime", name: "运行形态", tags: ["命令行", "CLI", "桌面应用", "Web应用", "移动App", "浏览器扩展", "后台服务"] },
  { id: "deployment", name: "部署方式", tags: ["自托管", "Docker", "K8s", "云服务", "本地运行", "私有部署"] },
  { id: "data_processing", name: "数据处理", tags: ["爬虫", "解析器", "ETL", "数据可视化", "备份", "同步", "迁移"] },
  { id: "network", name: "网络相关", tags: ["代理", "VPN", "反向代理", "负载均衡", "API网关", "内网穿透"] },
  { id: "storage", name: "存储相关", tags: ["数据库", "缓存", "对象存储", "网盘", "NAS", "向量数据库"] },
  { id: "media", name: "媒体处理", tags: ["图片处理", "视频处理", "音频处理", "OCR", "视频下载", "直播", "转码"] },
  { id: "ai", name: "AI相关", tags: ["LLM", "ChatGPT", "Claude", "Agent", "RAG", "图像生成", "语音合成"] },
  { id: "dev_tools", name: "开发工具", tags: ["编辑器", "IDE", "调试器", "API调试", "代码生成", "文档生成"] },
  { id: "devops", name: "运维监控", tags: ["监控", "日志", "告警", "CI/CD", "容器编排", "配置管理"] },
  { id: "security", name: "安全隐私", tags: ["密码管理", "加密", "认证", "权限", "扫描", "隐私保护"] },
  { id: "productivity", name: "效率办公", tags: ["笔记", "知识库", "任务管理", "书签", "截图", "翻译"] },
  { id: "content", name: "内容创作", tags: ["博客", "CMS", "静态站点", "Wiki", "Markdown", "写作"] },
  { id: "info", name: "信息获取", tags: ["RSS", "新闻聚合", "订阅", "搜索引擎", "监测"] },
  { id: "automation", name: "自动化", tags: ["脚本", "定时任务", "工作流", "Webhook", "RPA", "批量处理"] },
  { id: "life", name: "娱乐生活", tags: ["游戏", "音乐", "追剧", "记账", "健康", "旅行"] },
];

const TAG_TO_GROUP_MAP = new Map<string, TagGroup>();
TAG_GROUPS.forEach((group) => {
  group.tags.forEach((tag) => {
    TAG_TO_GROUP_MAP.set(tag, group);
  });
});

export function getTagGroup(tag: string): TagGroup | undefined {
  return TAG_TO_GROUP_MAP.get(tag);
}

export const ALL_TAGS = TAG_GROUPS.flatMap((group) => group.tags);
