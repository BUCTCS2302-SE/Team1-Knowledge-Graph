import os
import csv
import time
import random
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

class AsianArtResilientScraper:
    def __init__(self):
        self.root_url = "https://searchcollection.asianart.org"
        self.base_url = f"{self.root_url}/search/china/objects/list"
        self.csv_file = "o1.csv"
        self.fieldnames = ['Title', 'image_url', 'detail_url', 'Object number', 'Artist', 
                           'Date', 'Medium', 'Dimensions', 'Credit Line', 'Culture']

    def get_last_index(self):
        """读取 CSV 获取最后的图片编号"""
        if not os.path.exists(self.csv_file):
            return 0
        try:
            with open(self.csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                if not rows: return 0
                last_img_path = rows[-1].get('Img_path', '')
                match = re.search(r'asian_(\d+)', last_img_path)
                return int(match.group(1)) if match else len(rows)
        except Exception:
            return 0

    def save_row(self, row_data):
        file_exists = os.path.isfile(self.csv_file)
        current_keys = list(row_data.keys())
        for key in current_keys:
            if key not in self.fieldnames:
                self.fieldnames.append(key)
        if file_exists:
            with open(self.csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                existing_fields = list(reader.fieldnames) if reader.fieldnames else []
            for key in self.fieldnames:
                if key not in existing_fields:
                    existing_fields.append(key)
            rows = []
            with open(self.csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
            with open(self.csv_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=existing_fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
                writer.writerow(row_data)
        else:
            with open(self.csv_file, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
                writer.writerow(row_data)

    def scrape_detail(self, context, url, index):
        """抓取详情页，若失败则停下等待人工验证"""
        page = context.new_page()
        
        while True:  # 只有成功抓取或确定无数据才会 break
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                # 尝试等待详情字段出现
                try:
                    page.wait_for_selector(".detailField", timeout=8000)
                except:
                    # 如果没找到字段，说明可能跳了验证码
                    print(f"\n🛑 [拦截提示] 无法解析详情页内容: {url}")
                    print("👉 请在浏览器窗口检查是否出现了人机验证。")
                    input("👉 处理完成后，请按回车键重试当前页面...")
                    continue # 重新执行 while 循环里的 goto

                # 开始解析
                soup = BeautifulSoup(page.content(), 'html.parser')
                item_info = {"detail_url": url}
                
                title_tag = soup.select_one('.detailField')
                if not title_tag:
                    continue # 双重保险

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
                return item_info # 成功抓取，返回数据

            except Exception as e:
                print(f"⚠️ 网络错误或超时: {e}")
                input("👉 请检查网络或浏览器状态后，按回车重试...")
                continue

    def run(self, start_page=1, end_page=600):
        self.global_index = self.get_last_index()
        print(f"📊 索引初始化完毕，从 asian_{self.global_index + 1}.jpg 开始编号")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False) 
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            main_page = context.new_page()
            
            # 初始验证
            main_page.goto(self.base_url)
            print("\n" + "!"*50)
            print("🛡️ 请完成初始人机验证，看到列表后按回车开始。")
            print("!"*50 + "\n")
            input("👉 [已完成，启动自动爬取]...") 

            for p_num in range(start_page, end_page + 1):
                print(f"\n🚀 正在处理第 {p_num} 页...")
                try:
                    main_page.goto(f"{self.base_url}?page={p_num}", wait_until="networkidle", timeout=60000)
                    
                    # 检查列表页是否被拦截
                    try:
                        main_page.wait_for_selector("div.text-wrap", timeout=10000)
                    except:
                        print(f"🛑 列表页第 {p_num} 页似乎被拦截了！")
                        input("👉 请在浏览器处理验证后按回车重试该页...")
                        main_page.goto(f"{self.base_url}?page={p_num}", wait_until="networkidle")

                    links = main_page.eval_on_selector_all(
                        "div.text-wrap a", "elements => elements.map(e => e.href)"
                    )
                    
                    for link in links:
                        self.global_index += 1
                        data = self.scrape_detail(context, link, self.global_index)
                        if data:
                            self.save_row(data)
                            print(f"   ✅ [#{self.global_index}] {data.get('Title', '')[:12]}...")
                        time.sleep(random.uniform(1.2, 2)) # 稍微慢一点更安全

                except Exception as e:
                    print(f"❌ 列表页异常: {e}")
                    input("👉 请处理后回车重试...")
                    continue

            browser.close()

if __name__ == "__main__":
    scraper = AsianArtResilientScraper()
    # 记得根据实际进度调整 start_page
    scraper.run(start_page=65, end_page=600)