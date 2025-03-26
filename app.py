# -*- coding: utf-8 -*-
import os
import asyncio
import pandas as pd
from flask import Flask, render_template, request, send_from_directory, Response, jsonify, redirect, url_for, flash, session
from twikit import Client
import traceback # ★★★ tracebackモジュールをインポート ★★★
import json # エラー処理で使う可能性

# --- Flask アプリケーションの設定 ---
app = Flask(__name__)
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# 重要: Flaskのセッション機能には `secret_key` の設定が必須です。
# これは絶対に秘密にし、ランダムで予測困難な文字列を設定してください。
# 以下のキーは単なる例です。必ず変更してください！
# 環境変数 FLASK_SECRET_KEY から読み込むことを強く推奨します。
# 例: python -c "import os; print(os.urandom(24).hex())" で生成
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'CHANGE_THIS_TO_A_VERY_SECURE_RANDOM_KEY')
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'csv_exports')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- twikit 設定 ---
SCRAPE_TWEETS_COUNT = 50
SEARCH_TYPE = 'Latest'

# --- twikit 関連の非同期関数 ---
async def search_and_process_keyword(client, keyword):
    """【変更なし】指定されたキーワードで検索し、データをリストで返す"""
    print(f"キーワード '{keyword}' で検索中 (最大{SCRAPE_TWEETS_COUNT}件)...")
    tweets_data = []
    try:
        tweets = await client.search_tweet(
            keyword, SEARCH_TYPE, count=SCRAPE_TWEETS_COUNT
        )
        if tweets:
            print(f"  {len(tweets)} 件発見。処理中...")
            for tweet in tweets:
                user_name, screen_name, tweet_url = "N/A", "N/A", "N/A"
                if tweet.user:
                    user_name = tweet.user.name
                    screen_name = tweet.user.screen_name
                    tweet_url = f"https://twitter.com/{screen_name}/status/{tweet.id}"
                tweets_data.append({
                    'keyword': keyword, 'time': tweet.created_at, 'user_name': user_name,
                    'screen_name': screen_name, 'text': getattr(tweet, 'text', '').replace('\n', ' '),
                    'tweet_url': tweet_url, 'tweet_id': tweet.id,
                })
        else:
            print(f"  キーワード '{keyword}' でツイートが見つかりませんでした。")
    except Exception as e:
        print(f"!!! キーワード '{keyword}' の検索処理中にエラーが発生: {e}")
        raise e
    return tweets_data

# --- Flask ルート定義 ---

@app.before_request
def check_login_session():
    """【変更なし】リクエスト毎にセッションをチェック"""
    if request.endpoint and request.endpoint not in ('login', 'static'):
        if 'logged_in' not in session or not session['logged_in']:
            flash('このページにアクセスするにはログインが必要です。', 'info')
            return redirect(url_for('login'))

@app.route('/')
def index():
    """【変更なし】トップページ (検索フォームページ) を表示"""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """【修正】ログインページの表示と認証処理 (エラー詳細ログ出力追加)"""
    if session.get('logged_in'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        auth_info_1 = request.form.get('auth_info_1')
        password = request.form.get('password')
        login_error = None
        login_success = False

        if not auth_info_1 or not password:
            flash('ユーザー情報とパスワードの両方を入力してください。', 'danger')
            return render_template('login.html')

        try:
            # --- 非同期ログイン検証処理 ---
            # この async def ブロック内で twikit の login を呼び出します
            async def run_login_verification(): # 関数名は run_login_check でなくてもOK
                nonlocal login_success, login_error # 外側の変数を変更
                client = Client('ja-JP')
                try:
                    print(f"ユーザー '{auth_info_1}' のログイン検証試行...")
                    await client.login(auth_info_1=auth_info_1, password=password)
                    print("ログイン検証成功。")
                    login_success = True
                except Exception as e:
                    # --- ★★★ エラーログ強化 ここから ★★★ ---
                    print("-" * 20 + " twikit login エラー詳細 " + "-" * 20)
                    print(f"!!! twikitログイン検証中にエラーが発生: {type(e).__name__}: {e}")
                    print("--- Traceback ---")
                    traceback.print_exc() # 詳しいエラー情報をログに出力
                    print("--- End Traceback ---")
                    # --- ★★★ エラーログ強化 ここまで ★★★ ---
                    login_success = False # エラー発生時は失敗
                    login_error_detail = str(e).lower()
                    # (エラーメッセージ判定は前回と同様)
                    if 'challenge' in login_error_detail or 'verification' in login_error_detail or 'two factor' in login_error_detail:
                         login_error = f"ログイン検証失敗。2段階認証エラーの可能性。アプリパスワード等を試してください。 詳細: {e}"
                    elif 'incorrect' in login_error_detail or 'invalid' in login_error_detail:
                         login_error = f"ログイン検証失敗: ユーザー情報/パスワード間違いの可能性。 詳細: {e}"
                    else:
                         login_error = f"ログイン検証中にエラーが発生しました: {e}"

            # 非同期関数を実行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_login_verification()) # 上で定義した関数を実行
            loop.close()
            # --- 非同期ログイン検証処理ここまで ---

        except Exception as e:
            print(f"!!! Flaskログイン検証処理エラー: {e}")
            traceback.print_exc()
            login_error = f"ログイン検証処理中に予期せぬエラー: {e}"

        # ログイン結果の処理
        if login_success:
            session['logged_in'] = True
            session['username'] = auth_info_1
            session['password'] = password
            flash('ログイン成功！検索ページに移動します。', 'success')
            return redirect(url_for('index'))
        else:
            if login_error:
                flash(login_error, 'danger')
            else:
                flash('ログイン検証に失敗しました。原因不明のエラーです。', 'danger')
            return render_template('login.html')

    # GETリクエストの場合
    return render_template('login.html')

@app.route('/search', methods=['POST'])
def search():
    """【修正済】キーワードを受け取り、毎回ログインして検索を実行"""
    if 'logged_in' not in session or not session['logged_in'] or \
       'username' not in session or 'password' not in session:
         flash('ログイン情報がありません。再度ログインしてください。', 'danger')
         session.clear()
         return redirect(url_for('login'))

    keywords_input = request.form.get('keywords', '')
    search_keywords_list = [kw.strip() for kw in keywords_input.split(',') if kw.strip()]

    if not search_keywords_list:
        flash('検索キーワードが入力されていません。', 'warning')
        return render_template('index.html', keywords=keywords_input)

    auth_info_1 = session['username']
    password = session['password']

    csv_files_info = {}
    search_error = None
    try:
        # --- 非同期検索処理 (毎回ログインを含む) ---
        async def run_searches_with_relogin():
            nonlocal search_error, csv_files_info
            client = Client('ja-JP')
            logged_in_this_request = False
            try:
                print(f"検索実行のため、ユーザー '{auth_info_1}' で再ログイン試行...")
                try:
                    await client.login(auth_info_1=auth_info_1, password=password)
                    print("再ログイン成功。検索処理を開始します。")
                    logged_in_this_request = True
                except Exception as relogin_e:
                    print(f"!!! 検索時の再ログインに失敗: {relogin_e}")
                    # ★ 再ログイン失敗時もトレースバックを表示 ★
                    print("-" * 20 + " 再ログインエラー詳細 " + "-" * 20)
                    traceback.print_exc()
                    print("-" * 20)
                    search_error = f"検索実行前の再ログインに失敗しました: {relogin_e}"
                    session.clear() # セッションクリアして次回ログインを促す
                    raise Exception("再ログイン失敗のため処理中断") from relogin_e

                if logged_in_this_request:
                    print(f"検索キーワード: {search_keywords_list}")
                    for keyword in search_keywords_list:
                        try:
                            data = await search_and_process_keyword(client, keyword)
                            if data:
                                # (CSV保存処理 - 変更なし)
                                safe_keyword_part = "".join(c if c.isalnum() else "_" for c in keyword)[:50]
                                filename = f"{safe_keyword_part}.csv"
                                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                                df = pd.DataFrame(data)
                                columns_order = ['keyword', 'time', 'user_name', 'screen_name', 'text', 'tweet_url', 'tweet_id']
                                existing_columns = [col for col in columns_order if col in df.columns]
                                df_reordered = df.reindex(columns=existing_columns + [col for col in df.columns if col not in existing_columns])
                                df_reordered.to_csv(filepath, index=False, encoding='utf-8-sig')
                                csv_files_info[keyword] = filename
                                print(f"  キーワード '{keyword}' の検索結果を {filename} に保存しました。")
                            else:
                                print(f"  キーワード '{keyword}' でツイートが見つかりませんでした。")
                        except Exception as keyword_e:
                             print(f"!!! キーワード '{keyword}' の処理中にエラーが発生: {keyword_e}")
                             current_error = f"キーワード '{keyword}': {keyword_e}"
                             search_error = (search_error + "\n" + current_error) if search_error else current_error
                             error_str_lower = str(keyword_e).lower()
                             # 認証関連のエラーならループ中断＆セッションクリア
                             if "auth_token" in error_str_lower or "bad guest token" in error_str_lower or isinstance(keyword_e, json.JSONDecodeError) or "401" in error_str_lower or "unauthorized" in error_str_lower:
                                  search_error += " (ログイン認証に失敗した可能性があります)"
                                  session.clear()
                                  raise Exception("認証エラーのため全キーワードの処理を中断") from keyword_e
                        finally:
                             await asyncio.sleep(3) # 負荷軽減

            except Exception as e: # 再ログイン失敗 or 検索中の共通エラー
                print(f"!!! 検索処理中にエラーが発生: {e}")
                if not search_error:
                    search_error = f"検索処理中にエラーが発生しました: {e}"
            finally:
                pass # client.close()など

        # 非同期実行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_searches_with_relogin())
        loop.close()
        # --- 非同期検索処理ここまで ---

    except Exception as e:
        print(f"!!! Flask検索ルート処理全体でエラーが発生: {e}")
        traceback.print_exc()
        search_error = f"検索処理中に予期せぬエラーが発生しました: {e}"

    # --- 検索結果の表示 ---
    if search_error:
        flash(search_error, 'danger')
        if "再ログイン失敗" in search_error or "ログイン認証に失敗" in search_error:
             return redirect(url_for('login')) # 再ログインを促す
    if not csv_files_info and not search_error:
        flash('指定されたキーワードでツイートが見つかりませんでした。', 'info')
    elif csv_files_info and not search_error:
         flash('検索が完了し、以下のCSVファイルが生成されました。', 'success')

    return render_template('index.html', csv_files=csv_files_info, keywords=keywords_input)


@app.route('/download/<path:filename>')
def download_file(filename):
    """【変更なし】生成されたCSVファイルをダウンロードさせる"""
    try:
        safe_dir = os.path.abspath(app.config["UPLOAD_FOLDER"])
        safe_path = os.path.abspath(os.path.join(safe_dir, filename))
        if os.path.commonpath((safe_dir, safe_path)) != safe_dir:
             raise FileNotFoundError("不正なファイル名です。")
        if not os.path.isfile(safe_path):
             raise FileNotFoundError(f"ファイル '{filename}' がサーバー上に見つかりません。")
        return send_from_directory(directory=safe_dir, path=filename, as_attachment=True)
    except FileNotFoundError as e:
        print(f"!!! ファイルダウンロードエラー: {e}")
        flash(str(e), 'danger')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"!!! ファイルダウンロード中に予期せぬエラー: {e}")
        traceback.print_exc()
        flash(f"ファイルのダウンロード中にエラーが発生しました: {e}", 'danger')
        return redirect(url_for('index'))


@app.route('/logout')
def logout():
    """【変更なし】セッション情報をクリアしてログアウトする"""
    session.clear() # Flaskセッションの情報をすべて削除
    flash('ログアウトしました。', 'success')
    return redirect(url_for('login')) # ログアウト後はログインページへ

# --- アプリケーションの実行 ---
if __name__ == '__main__':
    print("Flask開発サーバーを起動します...")
    print(f"CSV出力先ディレクトリ: {app.config['UPLOAD_FOLDER']}")
    # ★★★ 重要 ★★★ Flask secret_key の設定確認
    if app.secret_key == 'a-very-complex-and-secret-key-please-change' or app.secret_key == 'dev_secret_key_please_change':
        print("\n" + "="*60)
        print("警告: Flask の secret_key が安全でない可能性があります！")
        print("必ず予測困難な秘密のキーに変更してください。")
        print("例: `python -c 'import os; print(os.urandom(24).hex())'` で生成")
        print("="*60 + "\n")

    # Flask 開発サーバーを起動
    # 公開環境では Gunicorn などの WSGI サーバーを使用してください。
    app.run(debug=True, host='127.0.0.1', port=5000)