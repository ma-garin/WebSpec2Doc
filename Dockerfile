# WebSpec2Doc 社内サーバ展開用イメージ
# Playwright 公式イメージ（Chromium 同梱・Python 3.12）をベースにする。
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# 依存を先にインストールしてレイヤキャッシュを効かせる
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体をコピー
COPY . .

# Playwright ブラウザはベースイメージに同梱済み
ENV PYTHONUNBUFFERED=1 \
    WEBSPEC2DOC_PORT=8765

EXPOSE 8765

# 社内サーバ展開時は WEBSPEC2DOC_TRUSTED_HOSTS で許可ホストを指定する
# （未指定ならローカルループバックのみ許可＝既定のセキュリティ態勢）
CMD ["python", "app.py"]
