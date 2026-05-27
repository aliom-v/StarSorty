#!/usr/bin/env bash
# StarSorty SQLite 数据库备份脚本
# 用法: ./scripts/backup_db.sh [数据库路径] [备份目录]
# 定时执行: crontab -e → 0 3 * * * /path/to/scripts/backup_db.sh

set -euo pipefail

DB_PATH="${1:-./api/data/starsorty.db}"
BACKUP_DIR="${2:-./backups}"
RETENTION_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 检查数据库是否存在
if [ ! -f "$DB_PATH" ]; then
    echo "❌ 数据库不存在: $DB_PATH"
    exit 1
fi

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 使用 SQLite .backup 命令确保一致性备份
BACKUP_FILE="$BACKUP_DIR/starsorty_${TIMESTAMP}.db"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# 压缩备份
gzip "$BACKUP_FILE"
echo "✅ 备份完成: ${BACKUP_FILE}.gz ($(du -h "${BACKUP_FILE}.gz" | cut -f1))"

# 清理旧备份
DELETED=$(find "$BACKUP_DIR" -name "starsorty_*.db.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "🗑  清理旧备份: ${DELETED} 个文件"
fi

# 统计当前备份数量
TOTAL=$(find "$BACKUP_DIR" -name "starsorty_*.db.gz" | wc -l)
echo "📦 当前备份数量: $TOTAL"
