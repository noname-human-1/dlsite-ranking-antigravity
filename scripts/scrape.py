import os
import re
import sys
import json
import time
import io
import urllib.request
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# Windows環境でのエンコーディングエラー対策
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 日本時間 (JST) のタイムゾーン定義
JST = timezone(timedelta(hours=+9))

# リポジトリ構造の定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates', 'index.html')
OUTPUT_PATH = os.path.join(BASE_DIR, 'index.html')

ACTIVE_WORKS_PATH = os.path.join(DATA_DIR, 'active_works.json')
EXCLUDED_WORKS_PATH = os.path.join(DATA_DIR, 'excluded_works.json')
STATUS_PATH = os.path.join(DATA_DIR, 'status.json')

# 必要なディレクトリの作成
os.makedirs(DATA_DIR, exist_ok=True)

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}")
            return default
    return default

def save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {path}: {e}")

def scrape_genre(category):
    print(f"Scraping category: {category}...")
    url = f'https://www.dlsite.com/maniax/ranking/day?category={category}&date=30d'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    req.add_header('Cookie', 'adultchecked=1; locale=ja_JP')
    
    works = []
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read()
            soup = BeautifulSoup(html, 'lxml')
            
            rows = soup.find_all('tr')
            for row in rows:
                rank_td = row.find('td', class_='ranking_count')
                if not rank_td:
                    continue
                    
                rank_no_div = rank_td.find('div', class_='rank_no')
                if not rank_no_div:
                    continue
                    
                rank = int(rank_no_div.text.strip())
                
                # Top30のみを対象とする
                if rank > 30:
                    continue
                    
                # 作品IDの抽出
                input_attr = row.find('input', class_='__product_attributes')
                product_id = ""
                if input_attr and input_attr.get('id'):
                    product_id = input_attr.get('id').lstrip('_')
                else:
                    work_name_a = row.find('dt', class_='work_name')
                    if work_name_a and work_name_a.find('a'):
                        href = work_name_a.find('a').get('href', '')
                        match = re.search(r'RJ\d+', href)
                        if match:
                            product_id = match.group(0)
                
                if not product_id:
                    continue
                
                # タイトル
                title = ""
                work_name_dt = row.find('dt', class_='work_name')
                if work_name_dt and work_name_dt.find('a'):
                    title = work_name_dt.find('a').text.strip()
                    
                # サークル名 & サークルID
                circle_name = ""
                circle_id = ""
                maker_name_dd = row.find('dd', class_='maker_name')
                if maker_name_dd and maker_name_dd.find('a'):
                    circle_name = maker_name_dd.find('a').text.strip()
                    circle_href = maker_name_dd.find('a').get('href', '')
                    match = re.search(r'RG\d+', circle_href)
                    if match:
                        circle_id = match.group(0)
                
                # サムネイルURL
                thumbnail_url = ""
                thumb_tag = row.find('thumb-with-ng-filter')
                if thumb_tag and thumb_tag.get(':thumb-candidates'):
                    try:
                        candidates_str = thumb_tag.get(':thumb-candidates')
                        candidates = json.loads(candidates_str.replace("'", '"'))
                        if candidates:
                            thumbnail_url = candidates[0]
                            if thumbnail_url.startswith('//'):
                                thumbnail_url = 'https:' + thumbnail_url
                    except Exception:
                        pass
                
                if not thumbnail_url:
                    img_tag = row.find('img')
                    if img_tag:
                        thumbnail_url = img_tag.get('src', '')
                        if thumbnail_url.startswith('//'):
                            thumbnail_url = 'https:' + thumbnail_url
                
                works.append({
                    'id': product_id,
                    'title': title,
                    'circle_name': circle_name,
                    'circle_id': circle_id,
                    'thumbnail_url': thumbnail_url,
                    'rank': rank
                })
        print(f"Successfully scraped {len(works)} works for category {category}")
    except Exception as e:
        print(f"Error scraping {category}: {e}")
        
    return works

def main():
    now = datetime.now(JST)
    current_date_str = now.strftime('%Y/%m/%d')
    current_datetime_str = now.strftime('%Y-%m-%d %H:%M')
    
    # 既存データのロード
    active_works = load_json(ACTIVE_WORKS_PATH, [])
    excluded_works = set(load_json(EXCLUDED_WORKS_PATH, []))
    status = load_json(STATUS_PATH, {})
    
    # 開始日の設定 (データが存在しない、またはリセット直後の場合)
    if not status.get('start_date') or not active_works:
        status['start_date'] = current_date_str
        print(f"Set start date to {current_date_str}")
        
    # スクレイピングの実行
    categories = {
        'comic': 'comic',
        'game': 'game',
        'voice': 'voice'
    }
    
    scraped_data = {}
    for cat_key, cat_val in categories.items():
        scraped_data[cat_key] = scrape_genre(cat_val)
        time.sleep(3) # DLsiteサーバー負荷防止のため3秒待機
        
    # 集約処理
    # active_works を辞書型に変換して更新しやすくする
    active_dict = {w['id']: w for w in active_works}
    
    for cat_key, works in scraped_data.items():
        for work in works:
            work_id = work['id']
            
            # 除外リストに入っている場合はスキップ
            if work_id in excluded_works:
                print(f"Skipping excluded work: {work_id} ({work['title'][:15]}...)")
                continue
                
            rank = work['rank']
            
            if work_id in active_dict:
                # 既に存在する場合は最高順位と最終確認日を更新
                existing = active_dict[work_id]
                existing['highest_rank'] = min(existing.get('highest_rank', 99), rank)
                existing['last_seen'] = current_date_str
                # 情報更新
                existing['title'] = work['title']
                existing['circle_name'] = work['circle_name']
                existing['circle_id'] = work['circle_id']
                if work['thumbnail_url']:
                    existing['thumbnail_url'] = work['thumbnail_url']
            else:
                # 新規作品を追加
                active_dict[work_id] = {
                    'id': work_id,
                    'title': work['title'],
                    'circle_name': work['circle_name'],
                    'circle_id': work['circle_id'],
                    'thumbnail_url': work['thumbnail_url'],
                    'category': cat_key,
                    'highest_rank': rank,
                    'first_seen': current_date_str,
                    'last_seen': current_date_str
                }
                print(f"Added new work: {work_id} ({work['title'][:15]}...)")
                
    # 辞書からリストに戻す
    updated_active_works = list(active_dict.values())
    
    # データを保存
    save_json(ACTIVE_WORKS_PATH, updated_active_works)
    
    # ステータス情報の更新
    status['last_updated'] = current_datetime_str
    
    # カテゴリごとに分類・ソート
    categories_data = {
        'comic': [],
        'game': [],
        'voice': []
    }
    
    for work in updated_active_works:
        cat = work.get('category')
        if cat in categories_data:
            categories_data[cat].append(work)
            
    # 各カテゴリ内で最高順位の昇順、作品IDの昇順でソート
    for cat in categories_data:
        categories_data[cat].sort(key=lambda x: (x.get('highest_rank', 99), x.get('id', '')))
        
    status['total_comic'] = len(categories_data['comic'])
    status['total_game'] = len(categories_data['game'])
    status['total_voice'] = len(categories_data['voice'])
    
    save_json(STATUS_PATH, status)
    
    # HTML生成
    if not os.path.exists(TEMPLATE_PATH):
        print(f"Error: Template file not found at {TEMPLATE_PATH}", file=sys.stderr)
        return
        
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = f.read()
        
    # カードHTMLの構築
    card_template = """
                    <div class="card">
                        <a class="thumb-container" href="https://www.dlsite.com/maniax/work/=/product_id/{id}.html" target="_blank" rel="noopener noreferrer">
                            <img class="thumb" src="{thumbnail_url}" loading="lazy">
                            <div class="badge-overlay-top">
                            </div>
                            <div class="badge-overlay-bottom">
                                <span class="badge badge-rank">最高 {highest_rank}位</span>
                            </div>
                        </a>
                        <div class="card-content">
                            <h3 class="work-title">
                                <a href="https://www.dlsite.com/maniax/work/=/product_id/{id}.html" target="_blank" rel="noopener noreferrer">{title}</a>
                            </h3>
                            <div class="circle-name">
                                <a href="https://www.dlsite.com/maniax/circle/profile/=/maker_id/{circle_id}.html" target="_blank" rel="noopener noreferrer">{circle_name}</a>
                                <a href="https://www.google.com/search?q={id}" target="_blank" rel="noopener noreferrer" class="badge badge-id-green">{id}</a>
                            </div>
                        </div>
                    </div>"""
                    
    no_data_html = '<div class="no-data">現在集約された作品はありません。</div>'
    
    html_cards = {}
    for cat, works in categories_data.items():
        if not works:
            html_cards[cat] = no_data_html
        else:
            cards_html = []
            for work in works:
                cards_html.append(card_template.format(
                    id=work['id'],
                    thumbnail_url=work['thumbnail_url'] if work['thumbnail_url'] else 'data:image/gif;base64,R0lGODlhAQABAGAAACH5BAEKAP8ALAAAAAABAAEAAAgEAP8FBAA7',
                    highest_rank=work['highest_rank'],
                    title=work['title'],
                    circle_id=work['circle_id'] if work['circle_id'] else '',
                    circle_name=work['circle_name'] if work['circle_name'] else 'サークル情報なし'
                ))
            html_cards[cat] = '\n'.join(cards_html)
            
    # GitHubリポジトリ情報の取得
    github_repo_env = os.environ.get('GITHUB_REPOSITORY', '')
    if '/' in github_repo_env:
        owner, repo = github_repo_env.split('/', 1)
    else:
        owner, repo = "noname-human-1", "dlsite-ranking" # フォールバックデフォルト値
        
    # テンプレートの置換
    html_output = template
    html_output = html_output.replace('{{START_DATE}}', status['start_date'])
    html_output = html_output.replace('{{END_DATE}}', current_date_str)
    html_output = html_output.replace('{{LAST_UPDATED}}', status['last_updated'])
    html_output = html_output.replace('{{COUNT_COMIC}}', str(status['total_comic']))
    html_output = html_output.replace('{{COUNT_GAME}}', str(status['total_game']))
    html_output = html_output.replace('{{COUNT_VOICE}}', str(status['total_voice']))
    html_output = html_output.replace('{{CARDS_COMIC}}', html_cards['comic'])
    html_output = html_output.replace('{{CARDS_GAME}}', html_cards['game'])
    html_output = html_output.replace('{{CARDS_VOICE}}', html_cards['voice'])
    html_output = html_output.replace('{{GITHUB_OWNER}}', owner)
    html_output = html_output.replace('{{GITHUB_REPO}}', repo)
    
    # index.htmlの書き出し
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html_output)
        
    print(f"Generated index.html successfully. Total works: {len(updated_active_works)}")

if __name__ == '__main__':
    main()
