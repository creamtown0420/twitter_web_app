# -*- coding: utf-8 -*-
import os
import asyncio
import json
import tempfile
import traceback # エラー詳細表示用
from flask import Flask, render_template, request, redirect, url_for, session, flash
from twikit import Client
# from twikit.errors import TwitterException # twikitのエラーを具体的に補足する場合

app = Flask(__name__)
# Flaskのセッション機能を使うにはsecret_keyが必須です。
# 必ずランダムで安全な文字列に変更してください。
# Renderの環境変数に設定することを強く推奨します。
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_very_secret_and_random_key_fallback')

# --- twikit クライアント初期化 (非同期関数内で使用) ---
# client = Client('ja') # グローバルには置かず、各関数内で初期化する

# --- ルート定義 ---

@app.route('/')
def index():
    """ ログイン状態に応じて表示を切り替える """
    if 'twikit_cookies' in session:
        # ログイン済みなら検索ページへ
        return render_template('search.html')
    else:
        # 未ログインならログインページへ
        return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
async def login():
    """ ログイン処理 """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # email = request.form.get('email') # 必要なら

        if not username or not password:
            flash('ユーザー名とパスワードを入力してください。', 'error')
            return render_template('login.html')

        client = Client('ja')
        cookie_filepath = None # finally で使うため

        try:
            print(f"ユーザー '{username}' のログイン試行...")
            # --- ログイン実行 ---
            await client.login(
                auth_info_1=username,
                password=password
                # auth_info_2=email, # 必要ならコメント解除
            )
            print("ログイン成功。Cookie情報を取得・保存します...")

            # --- Cookie情報を一時ファイル経由で取得し、セッションに保存 ---
            # NamedTemporaryFileで確実に一時ファイルを作成・管理
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8') as tmp_cookie_file:
                cookie_filepath = tmp_cookie_file.name
                client.save_cookies(cookie_filepath) # 一時ファイルに保存

            # 一時ファイルから内容を読み込んでセッションに保存
            with open(cookie_filepath, 'r', encoding='utf-8') as f:
                cookie_data = json.load(f)
            session['twikit_cookies'] = cookie_data # 辞書としてセッションに保存
            print("Cookie情報をセッションに保存しました。")

            flash('ログインに成功しました！', 'success')
            return redirect(url_for('search_page')) # 検索ページへリダイレクト

        except Exception as e:
            # twikitのエラーは種類が多いので、一旦まとめて捕捉
            error_type = type(e).__name__
            error_message = str(e)
            print(f"!!! ログイン失敗: {error_type}: {error_message}")
            traceback.print_exc() # 詳細なトレースバックをログに出力
            # 特に 'BadRequest: status: 400, message: "Missing data..."' が発生するか確認
            flash(f'ログインに失敗しました: {error_message}', 'error')
            return render_template('login.html')

        finally:
            # 一時ファイルを確実に削除
            if cookie_filepath and os.path.exists(cookie_filepath):
                try:
                    os.remove(cookie_filepath)
                    print("一時Cookieファイルを削除しました。")
                except OSError as remove_err:
                    print(f"!!! 一時Cookieファイルの削除に失敗: {remove_err}")

    # GETリクエストの場合 or ログイン失敗後の再表示
    return render_template('login.html')

@app.route('/search', methods=['GET', 'POST'])
async def search_page():
    """ 検索ページ表示と検索実行 """
    # --- ログイン状態(セッションのCookie)を確認 ---
    cookie_data = session.get('twikit_cookies')
    if not cookie_data:
        flash('ログインが必要です。', 'warning')
        return redirect(url_for('login'))

    client = Client('ja')
    cookie_filepath = None # finally 用
    results = []
    keyword = ""

    # --- Cookieデータをクライアントに設定 ---
    try:
        # セッションのCookieデータを一時ファイルに書き出す
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8') as tmp_cookie_file:
            json.dump(cookie_data, tmp_cookie_file)
            cookie_filepath = tmp_cookie_file.name

        client.load_cookies(cookie_filepath) # 一時ファイルからCookieを読み込む
        print("セッションからCookieを読み込み、クライアントに設定しました。")

    except Exception as load_err:
        print(f"!!! Cookieの読み込み/設定エラー: {load_err}")
        traceback.print_exc()
        session.pop('twikit_cookies', None) # エラー時はセッションをクリア
        flash('セッション情報の読み込みに失敗しました。再ログインしてください。', 'error')
        return redirect(url_for('login'))
    finally:
            # 一時ファイルを確実に削除
            if cookie_filepath and os.path.exists(cookie_filepath):
                try:
                    os.remove(cookie_filepath)
                    print("一時Cookieファイル(読み込み用)を削除しました。")
                except OSError as remove_err:
                    print(f"!!! 一時Cookieファイル(読み込み用)の削除に失敗: {remove_err}")

    # --- 検索実行 (POSTリクエストの場合) ---
    if request.method == 'POST':
        keyword = request.form.get('keyword')
        if not keyword:
            flash('検索キーワードを入力してください。', 'warning')
        else:
            try:
                print(f"キーワード '{keyword}' でツイートを検索します...")
                # product="Latest" で新しい順、"Top"で話題順
                tweets = await client.search_tweet(query=keyword, product='Latest', count=50) # count は適宜調整
                print(f"{len(tweets)} 件のツイートが見つかりました。")

                for tweet in tweets:
                    results.append({
                        'id': tweet.id,
                        'user_name': getattr(tweet.user, 'name', 'N/A'), # ユーザー情報が取得できるか試す
                        'screen_name': getattr(tweet.user, 'screen_name', 'N/A'),
                        'created_at': tweet.created_at_datetime.strftime('%Y-%m-%d %H:%M:%S') if tweet.created_at_datetime else 'N/A',
                        'text': tweet.text,
                        'url': f"https://twitter.com/{getattr(tweet.user, 'screen_name', 'i')}/status/{tweet.id}" if getattr(tweet.user, 'screen_name', None) else ""
                        # 他に必要な情報を追加
                    })

            except Exception as search_err:
                # 例: twikit.errors.Forbidden: 403 Forbidden: The request is not allowed -> Cookie切れの可能性
                error_type = type(search_err).__name__
                error_message = str(search_err)
                print(f"!!! 検索エラー: {error_type}: {error_message}")
                traceback.print_exc()
                # Cookieが無効になった可能性があればセッションをクリア
                # (エラーの種類を特定して判定するのが望ましい)
                session.pop('twikit_cookies', None)
                flash(f'ツイートの検索中にエラーが発生しました。Cookieが無効になった可能性があります。再ログインしてください。\n({error_message})', 'error')
                return redirect(url_for('login')) # エラー時はログインページへ

    # GETリクエストまたは検索実行後
    return render_template('search.html', keyword=keyword, results=results)

@app.route('/logout')
def logout():
    """ ログアウト処理 (セッションからCookie情報を削除) """
    session.pop('twikit_cookies', None)
    flash('ログアウトしました。', 'info')
    return redirect(url_for('login'))

# --- アプリ実行 ---
if __name__ == '__main__':
    # Flaskの開発サーバーで実行 (デバッグ用)
    # RenderではGunicornが使われるため、ここは直接実行されない
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))