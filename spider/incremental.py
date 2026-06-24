"""
增量爬取公共框架

提供三个核心能力：
1. IncrementalTracker - 指纹比对，识别新增/更新/未变的记录
2. CrawlLogger - 记录每次爬取的时间、数量与变更详情
3. 增量 CSV 写入 - 仅追加新增和更新的记录

使用方式：
    from incremental import IncrementalTracker, CrawlLogger

    tracker = IncrementalTracker('spider/xxx')
    logger = CrawlLogger('spider/xxx')

    # 爬取一条记录后
    record_id = 'OBJ123'
    record_data = {'Title': 'Vase', 'Date': '1800', ...}
    change_type = tracker.check(record_id, record_data)
    # change_type: 'new' / 'updated' / 'unchanged'

    # 批量结束后
    logger.log(tracker.get_stats())
    tracker.save()
"""

import os
import csv
import json
import hashlib
from datetime import datetime


class IncrementalTracker:
    """增量爬取指纹追踪器

    为每条爬取记录计算内容哈希，与历史哈希比对，
    判断该记录是新增、更新还是未变化。

    指纹文件格式: {museum_dir}/.crawl_fingerprints.json
    {
        "last_crawl_time": "2026-06-07T10:30:00",
        "fingerprints": {
            "OBJ123": "a1b2c3d4...",   # content hash
            "OBJ456": "e5f6g7h8...",
        }
    }
    """

    FINGERPRINT_FILE = '.crawl_fingerprints.json'

    def __init__(self, museum_dir):
        """
        Args:
            museum_dir: 博物馆目录路径，指纹文件存放在此目录下
        """
        self.museum_dir = museum_dir
        self.fp_path = os.path.join(museum_dir, self.FINGERPRINT_FILE)
        self.fingerprints = {}       # {record_id: hash}
        self.last_crawl_time = None

        # 本次爬取统计
        self.stats = {
            'new': 0,
            'updated': 0,
            'unchanged': 0,
            'new_ids': [],
            'updated_ids': [],
        }

        self._load()

    def _load(self):
        """加载历史指纹文件"""
        if os.path.exists(self.fp_path):
            try:
                with open(self.fp_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.fingerprints = data.get('fingerprints', {})
                self.last_crawl_time = data.get('last_crawl_time')
            except (json.JSONDecodeError, IOError):
                self.fingerprints = {}

    def _compute_hash(self, record_data):
        """计算记录的内容哈希

        将记录的所有值拼接后取 MD5，忽略键的顺序。
        """
        # 按 key 排序确保顺序一致
        content = json.dumps(record_data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def check(self, record_id, record_data):
        """检查单条记录的变更类型

        Args:
            record_id: 记录唯一标识（如 object_id, uuid, detail_url）
            record_data: 记录数据字典

        Returns:
            'new' | 'updated' | 'unchanged'
        """
        new_hash = self._compute_hash(record_data)
        old_hash = self.fingerprints.get(record_id)

        if old_hash is None:
            self.stats['new'] += 1
            self.stats['new_ids'].append(str(record_id))
            self.fingerprints[record_id] = new_hash
            return 'new'
        elif old_hash != new_hash:
            self.stats['updated'] += 1
            self.stats['updated_ids'].append(str(record_id))
            self.fingerprints[record_id] = new_hash
            return 'updated'
        else:
            self.stats['unchanged'] += 1
            return 'unchanged'

    def get_stats(self):
        """获取本次爬取统计"""
        return dict(self.stats)

    def save(self):
        """保存指纹文件"""
        os.makedirs(self.museum_dir, exist_ok=True)
        data = {
            'last_crawl_time': datetime.now().isoformat(),
            'total_records': len(self.fingerprints),
            'fingerprints': self.fingerprints,
        }
        with open(self.fp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def is_seen(self, record_id):
        """快速判断记录是否已存在（无需计算hash）"""
        return record_id in self.fingerprints


class CrawlLogger:
    """爬取变更日志记录器

    每次爬取结束后追加一条日志记录，包含：
    - 爬取时间
    - 新增/更新/未变数量
    - 新增和更新的记录ID列表

    日志文件格式: {museum_dir}/crawl_log.csv
    """

    LOG_FILE = 'crawl_log.csv'
    LOG_COLUMNS = [
        'crawl_time', 'new_count', 'updated_count', 'unchanged_count',
        'total_scanned', 'new_ids', 'updated_ids'
    ]

    def __init__(self, museum_dir):
        self.museum_dir = museum_dir
        self.log_path = os.path.join(museum_dir, self.LOG_FILE)

    def log(self, stats):
        """记录一次爬取日志

        Args:
            stats: IncrementalTracker.get_stats() 返回的统计字典
        """
        os.makedirs(self.museum_dir, exist_ok=True)
        file_exists = os.path.exists(self.log_path) and os.path.getsize(self.log_path) > 0

        row = {
            'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'new_count': stats.get('new', 0),
            'updated_count': stats.get('updated', 0),
            'unchanged_count': stats.get('unchanged', 0),
            'total_scanned': stats.get('new', 0) + stats.get('updated', 0) + stats.get('unchanged', 0),
            'new_ids': ';'.join(str(x) for x in stats.get('new_ids', [])),
            'updated_ids': ';'.join(str(x) for x in stats.get('updated_ids', [])),
        }

        with open(self.log_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=self.LOG_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def get_last_log(self):
        """获取最近一次爬取日志"""
        if not os.path.exists(self.log_path):
            return None
        try:
            with open(self.log_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                return rows[-1] if rows else None
        except Exception:
            return None

    def print_summary(self, stats):
        """打印本次爬取摘要"""
        new = stats.get('new', 0)
        updated = stats.get('updated', 0)
        unchanged = stats.get('unchanged', 0)
        total = new + updated + unchanged

        print(f"\n{'='*50}")
        print(f"爬取摘要")
        print(f"{'='*50}")
        print(f"  扫描记录数: {total}")
        print(f"  新增: {new}")
        print(f"  更新: {updated}")
        print(f"  未变化: {unchanged}")
        if new > 0:
            ids = stats.get('new_ids', [])
            preview = ids[:10]
            suffix = f" ...等{len(ids)}项" if len(ids) > 10 else ""
            print(f"  新增ID: {', '.join(str(x) for x in preview)}{suffix}")
        if updated > 0:
            ids = stats.get('updated_ids', [])
            preview = ids[:10]
            suffix = f" ...等{len(ids)}项" if len(ids) > 10 else ""
            print(f"  更新ID: {', '.join(str(x) for x in preview)}{suffix}")
        print(f"{'='*50}\n")


class IncrementalCSVWriter:
    """增量 CSV 写入器

    仅写入新增和更新的记录到 CSV 文件。
    对于更新的记录，替换原文件中对应行。
    """

    def __init__(self, csv_path, id_column, fieldnames=None):
        """
        Args:
            csv_path: CSV 文件路径
            id_column: 用作唯一标识的列名
            fieldnames: 列名列表，None 则自动推断
        """
        self.csv_path = csv_path
        self.id_column = id_column
        self.fieldnames = fieldnames

    def write(self, records, change_types):
        """写入记录

        Args:
            records: 记录列表 [dict, ...]
            change_types: 与 records 等长的变更类型列表 ['new'|'updated'|'unchanged', ...]
        """
        if not records:
            return

        # 确定列名
        if self.fieldnames is None:
            self.fieldnames = list(records[0].keys())

        # 读取已有数据
        existing = {}
        existing_order = []
        if os.path.exists(self.csv_path):
            try:
                for enc in ['utf-8-sig', 'utf-8', 'gbk']:
                    try:
                        with open(self.csv_path, 'r', encoding=enc) as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                rid = row.get(self.id_column, '')
                                existing[rid] = row
                                existing_order.append(rid)
                        break
                    except UnicodeDecodeError:
                        continue
            except Exception:
                pass

        # 合并新数据
        for record, ct in zip(records, change_types):
            if ct in ('new', 'updated'):
                rid = record.get(self.id_column, '')
                existing[rid] = record
                if ct == 'new':
                    existing_order.append(rid)

        # 写回文件
        dir_path = os.path.dirname(self.csv_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(self.csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames, extrasaction='ignore')
            writer.writeheader()
            for rid in existing_order:
                if rid in existing:
                    writer.writerow(existing[rid])
