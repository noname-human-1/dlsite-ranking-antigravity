import os
import sys
import json
import io
import urllib.request
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

def main():
    now = datetime.now(JST)
    current_datetime_str = now.strftime('%Y-%m-%d %H:%M')
    
    # 既存データのロード
    active_works = load_json(ACTIVE_WORKS_PATH, [])
    excluded_works = load_json(EXCLUDED_WORKS_PATH, [])
    
    # 現在アクティブな作品IDをすべて除外リストに追加
    active_ids = [w['id'] for w in active_works if 'id' in w]
    
    # 重複排除しながら追加
    new_excluded = list(set(excluded_works + active_ids))
    
    # 除外リストを保存
    save_json(EXCLUDED_WORKS_PATH, new_excluded)
    print(f"Moved {len(active_ids)} works to exclusion list. Total excluded works: {len(new_excluded)}")
    
    # アクティブリストをクリア
    save_json(ACTIVE_WORKS_PATH, [])
    
    # ステータスを初期化
    status = {
        'start_date': '',
        'last_updated': current_datetime_str,
        'total_comic': 0,
        'total_game': 0,
        'total_voice': 0
    }
    save_json(STATUS_PATH, status)
    
    # 空のHTMLを再生成する
    if not os.path.exists(TEMPLATE_PATH):
        print(f"Error: Template file not found at {TEMPLATE_PATH}", file=sys.stderr)
        return
        
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = f.read()
        
    no_data_html = '<div class="no-data">現在集約された作品はありません。</div>'
    
    # GitHubリポジトリ情報の取得
    github_repo_env = os.environ.get('GITHUB_REPOSITORY', '')
    if '/' in github_repo_env:
        owner, repo = github_repo_env.split('/', 1)
    else:
        owner, repo = "noname-human-1", "dlsite-ranking" # デフォルト値
        
    # テンプレートの置換 (空のデータ)
    html_output = template
    html_output = html_output.replace('{{START_DATE}}', '-')
    html_output = html_output.replace('{{END_DATE}}', '-')
    html_output = html_output.replace('{{LAST_UPDATED}}', status['last_updated'])
    html_output = html_output.replace('{{COUNT_COMIC}}', '0')
    html_output = html_output.replace('{{COUNT_GAME}}', '0')
    html_output = html_output.replace('{{COUNT_VOICE}}', '0')
    html_output = html_output.replace('{{CARDS_COMIC}}', no_data_html)
    html_output = html_output.replace('{{CARDS_GAME}}', no_data_html)
    html_output = html_output.replace('{{CARDS_VOICE}}', no_data_html)
    html_output = html_output.replace('{{GITHUB_OWNER}}', owner)
    html_output = html_output.replace('{{GITHUB_REPO}}', repo)
    
    # index.htmlの書き出し
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html_output)
        
    print("Successfully reset data and generated empty index.html")

if __name__ == '__main__':
    main()
