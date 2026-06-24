"""
大都会博物馆爬虫 - 支持增量爬取

增量爬取策略：
- 以 Object URL (detail_url) 作为记录唯一标识
- 首次全量爬取，后续仅爬取新增或更新的记录
- 通过对比 objectID 列表快速识别新增文物
- 对已有记录重新请求详情以检测字段更新
- 每次爬取结束后记录变更日志
"""
import os
import sys
import csv
import json
import time
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from incremental import IncrementalTracker, CrawlLogger, IncrementalCSVWriter

import requests
import pandas as pd


MET_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(MET_DIR, "daduihui_en.csv")
FAILED_FILE = os.path.join(MET_DIR, "failed_ids.csv")
ID_CACHE_FILE = os.path.join(MET_DIR, ".met_object_ids.json")


def get_object_details(object_id):
    """获取单个文物详细信息"""
    url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            title = data.get('title', 'Unknown')
            period = data.get('objectDate', 'Unknown')
            medium = data.get('medium', 'Unknown')
            primary_image = data.get('primaryImage', None)
            primary_image_url = 'Unknown' if not primary_image else primary_image
            object_url = data.get('objectURL', 'Unknown')
            artist = data.get('artistDisplayName', 'Unknown')
            if not artist:
                artist = 'Unknown'

            return {
                'Object ID': object_id,
                'Title': title,
                'Period': period,
                'Medium': medium,
                'Image': primary_image,
                'Image Download Link': primary_image_url,
                'Object URL': object_url,
                'Artist': artist
            }
        else:
            print(f"请求失败: {object_id}, 状态码: {response.status_code}")
            return None
    except Exception as e:
        print(f"请求异常: {object_id}, 错误: {str(e)}")
        return None


def get_china_object_ids():
    """获取所有中国文物ID列表"""
    base_url = "https://collectionapi.metmuseum.org/public/collection/v1/search"
    keywords = ["China", "Chinese"]
    all_ids = set()

    for keyword in keywords:
        params = {"q": keyword}
        while True:
            try:
                response = requests.get(base_url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    ids = data.get("objectIDs", [])
                    all_ids.update(ids)
                    print(f"关键词 '{keyword}' 找到 {len(ids)} 个结果")
                    next_page = data.get('next', None)
                    if next_page:
                        params['page'] = next_page
                    else:
                        break
                else:
                    print(f"关键词 '{keyword}' 请求失败: 状态码 {response.status_code}")
                    break
            except Exception as e:
                print(f"搜索请求异常: {e}")
                break

    print(f"总计去重后的文物ID数量: {len(all_ids)}")
    return sorted(list(all_ids))


def load_cached_ids():
    """加载上次缓存的 objectID 列表"""
    if os.path.exists(ID_CACHE_FILE):
        try:
            with open(ID_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return set(data.get('ids', []))
        except Exception:
            pass
    return set()


def save_cached_ids(ids):
    """保存 objectID 列表缓存"""
    with open(ID_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump({'ids': sorted(list(ids)), 'saved_at': time.strftime('%Y-%m-%d %H:%M:%S')}, f)


def fetch_and_save_china_data():
    """主函数：增量获取数据并保存为CSV"""
    tracker = IncrementalTracker(MET_DIR)
    logger = CrawlLogger(MET_DIR)

    last_crawl = tracker.last_crawl_time
    if last_crawl:
        print(f"上次爬取时间: {last_crawl}")
        print(f"历史指纹数: {len(tracker.fingerprints)}")
    else:
        print("首次爬取，将全量获取数据")

    # 获取当前所有 objectID
    current_ids = get_china_object_ids()
    if not current_ids:
        print("未找到任何中国文物ID")
        return

    # 筛选 ID
    filtered_ids = [obj_id for obj_id in current_ids if obj_id > 461499]
    print(f"筛选后文物数量: {len(filtered_ids)}")

    # 与缓存对比，识别新增 ID
    cached_ids = load_cached_ids()
    current_id_set = set(filtered_ids)
    new_ids = current_id_set - cached_ids
    existing_ids = current_id_set & cached_ids

    print(f"新增文物ID: {len(new_ids)}")
    print(f"已有文物ID: {len(existing_ids)}（将检查更新）")

    # 优先爬取新增文物，然后检查已有文物是否有更新
    ids_to_crawl = sorted(list(new_ids)) + sorted(list(existing_ids))

    # 读取已有 CSV 数据
    existing_csv_data = {}
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
            for _, row in df.iterrows():
                obj_url = str(row.get('Object URL', ''))
                if obj_url and obj_url != 'Unknown':
                    existing_csv_data[obj_url] = row.to_dict()
        except Exception:
            pass

    # 爬取数据
    data = []
    failed_ids = []
    header_written = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
    failed_header_written = os.path.exists(FAILED_FILE) and os.path.getsize(FAILED_FILE) > 0

    for idx, object_id in enumerate(ids_to_crawl, 1):
        if idx % 5 == 0:
            time.sleep(1)

        is_new = object_id in new_ids
        prefix = "[新增]" if is_new else "[检查]"
        print(f"{prefix} 正在处理第 {idx}/{len(ids_to_crawl)} 个文物: ID {object_id}")

        details = get_object_details(object_id)
        if details:
            # 增量检测：以 Object URL 为唯一标识
            record_id = details.get('Object URL', str(object_id))
            change_type = tracker.check(record_id, details)

            if change_type == 'new':
                data.append(details)
                print(f"  [+] 新增: {details.get('Title', '')[:40]}")
            elif change_type == 'updated':
                data.append(details)
                print(f"  [~] 更新: {details.get('Title', '')[:40]}")
            else:
                print(f"  [=] 未变化: {details.get('Title', '')[:40]}")

            # 批量保存新增和更新的记录
            if len(data) >= 10:
                _save_batch(data, CSV_FILE, header_written)
                header_written = True
                data = []
        else:
            failed_ids.append({'Object ID': object_id, 'Error': '获取详情失败'})
            if len(failed_ids) >= 10:
                _save_failed_batch(failed_ids, FAILED_FILE, failed_header_written)
                failed_header_written = True
                failed_ids = []

    # 保存剩余数据
    if data:
        _save_batch(data, CSV_FILE, header_written)

    if failed_ids:
        _save_failed_batch(failed_ids, FAILED_FILE, failed_header_written)

    # 更新 ID 缓存
    save_cached_ids(current_id_set)

    # 保存指纹和日志
    tracker.save()
    stats = tracker.get_stats()
    logger.log(stats)
    logger.print_summary(stats)


def _save_batch(data, path, header_written):
    """保存一批数据到CSV"""
    df = pd.DataFrame(data)
    df.to_csv(path, index=False, encoding="utf-8", mode='a', header=not header_written)
    print(f"  已保存 {len(data)} 条数据")


def _save_failed_batch(failed_ids, path, header_written):
    """保存失败记录"""
    df = pd.DataFrame(failed_ids)
    df.to_csv(path, index=False, encoding="utf-8", mode='a', header=not header_written)
    print(f"  已保存 {len(failed_ids)} 条失败记录")


if __name__ == "__main__":
    fetch_and_save_china_data()
