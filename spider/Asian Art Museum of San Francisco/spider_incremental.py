"""
旧金山亚洲艺术博物馆爬虫 - 支持增量爬取

增量爬取策略：
- 以 detail_url 作为记录唯一标识
- 对每条记录计算内容哈希，与历史指纹比对
- 仅保存新增或更新的记录
- 跳过内容未变化的记录（但仍会访问页面以检测更新）
- 每次爬取结束后记录变更日志
"""
import os
import sys
import csv
import time
import random
import re

# 将 spider 目录加入路径以导入公共模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from incremental import IncrementalTracker, CrawlLogger, IncrementalCSVWriter

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


class AsianArtIncrementalScraper:
    def __init__(self):
        self.root_url = "https://searchcollection.asianart.org"
        self.base_url = f"{self.root_url}/search/china/objects/list"
        self.museum_dir = os.path.dirname(os.path.abspath(__file__))
        self.csv_file = os.path.join(self.museum_dir, "o1.csv")
        self.fieldnames = ['Title', 'image_url', 'detail_url', 'Object number', 'Artist',
                           'Date', 'Medium', 'Dimensions', 'Credit Line', 'Culture']

        # 增量爬取组件
        self.tracker = IncrementalTracker(self.museum_dir)
        self.logger = CrawlLogger(self.museum_dir)

    def get_last_index(self):
        """读取 CSV 获取已爬取行数，用于断点续爬"""
        if not os.path.exists(self.csv_file):
            return 0
        try:
            with open(self.csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                return len(rows)
        except Exception:
            return 0

    def save_row(self, row_data, change_type):
        """保存单条记录（仅新增和更新时写入）

        Args:
            row_data: 记录数据字典
            change_type: 'new' | 'updated' | 'unchanged'
        """
        if change_type == 'unchanged':
            return  # 未变化，不写入

        file_exists = os.path.isfile(self.csv_file)
        current_keys = list(row_data.keys())
        for key in current_keys:
            if key not in self.fieldnames:
                self.fieldnames.append(key)

        if file_exists:
            with open(self.csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                existing_fields = list(reader.fieldnames) if reader.fieldnames else []
                rows = list(reader)

            for key in self.fieldnames:
                if key not in existing_fields:
                    existing_fields.append(key)

            # 如果是更新，替换已有行
            detail_url = row_data.get('detail_url', '')
            rows = [r for r in rows if r.get('detail_url', '') != detail_url]
            rows.append(row_data)

            with open(self.csv_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=existing_fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
        else:
            with open(self.csv_file, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
                writer.writerow(row_data)

    def scrape_detail(self, context, url, index):
        """抓取详情页，若失败则停下等待人工验证"""
        page = context.new_page()

        while True:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_selector(".detailField", timeout=8000)
                except:
                    print(f"\n[拦截提示] 无法解析详情页内容: {url}")
                    print("请在浏览器窗口检查是否出现了人机验证。")
                    input("处理完成后，请按回车键重试当前页面...")
                    continue

                soup = BeautifulSoup(page.content(), 'html.parser')
                item_info = {"detail_url": url}

                title_tag = soup.select_one('.detailField')
                if not title_tag:
                    continue

                item_info['Title'] = title_tag.get_text(strip=True)

                detail_blocks = soup.select('.detailField')
                for block in detail_blocks:
                    label = block.select_one('.detailFieldLabel')
                    value = block.select_one('.detailFieldValue')
                    if label and value:
                        key = label.get_text(strip=True).rstrip(':')
                        val = value.get_text(separator=' ', strip=True)
                        item_info[key] = val

                img_tag = soup.select_one("div.emuseum-img-wrap img")
                if img_tag and img_tag.get('src'):
                    img_url = self.root_url + img_tag['src'] if img_tag['src'].startswith('/') else img_tag['src']
                    item_info['image_url'] = img_url

                page.close()
                return item_info

            except Exception as e:
                print(f"网络错误或超时: {e}")
                input("请检查网络或浏览器状态后，按回车重试...")
                continue

    def run(self, start_page=1, end_page=600):
        self.global_index = self.get_last_index()
        last_crawl = self.tracker.last_crawl_time
        if last_crawl:
            print(f"上次爬取时间: {last_crawl}")
            print(f"历史指纹数: {len(self.tracker.fingerprints)}")
        print(f"索引初始化完毕，已有 {self.global_index} 条记录")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            main_page = context.new_page()
            main_page.goto(self.base_url)
            print("\n" + "!" * 50)
            print("请完成初始人机验证，看到列表后按回车开始。")
            print("!" * 50 + "\n")
            input("[已完成，启动自动爬取]...")

            for p_num in range(start_page, end_page + 1):
                print(f"\n正在处理第 {p_num} 页...")
                try:
                    main_page.goto(f"{self.base_url}?page={p_num}", wait_until="networkidle", timeout=60000)

                    try:
                        main_page.wait_for_selector("div.text-wrap", timeout=10000)
                    except:
                        print(f"列表页第 {p_num} 页似乎被拦截了！")
                        input("请在浏览器处理验证后按回车重试该页...")
                        main_page.goto(f"{self.base_url}?page={p_num}", wait_until="networkidle")

                    links = main_page.eval_on_selector_all(
                        "div.text-wrap a", "elements => elements.map(e => e.href)"
                    )

                    for link in links:
                        self.global_index += 1
                        data = self.scrape_detail(context, link, self.global_index)
                        if data:
                            # 增量检测：以 detail_url 为唯一标识
                            record_id = data.get('detail_url', link)
                            change_type = self.tracker.check(record_id, data)

                            if change_type == 'new':
                                self.save_row(data, change_type)
                                print(f"   [+] [#{self.global_index}] 新增: {data.get('Title', '')[:30]}...")
                            elif change_type == 'updated':
                                self.save_row(data, change_type)
                                print(f"   [~] [#{self.global_index}] 更新: {data.get('Title', '')[:30]}...")
                            else:
                                print(f"   [=] [#{self.global_index}] 未变化: {data.get('Title', '')[:30]}...")

                        time.sleep(random.uniform(1.2, 2))

                except Exception as e:
                    print(f"列表页异常: {e}")
                    input("请处理后回车重试...")
                    continue

            browser.close()

        # 保存指纹和日志
        self.tracker.save()
        stats = self.tracker.get_stats()
        self.logger.log(stats)
        self.logger.print_summary(stats)


if __name__ == "__main__":
    scraper = AsianArtIncrementalScraper()
    scraper.run(start_page=1, end_page=600)
