#!/bin/zsh
cd "$(dirname "$0")"

echo "=============================="
echo "  WebSpec2Doc"
echo "=============================="
echo ""

read "url?クロール対象URL: "

if [[ -z "$url" ]]; then
  echo "URL が入力されていません。終了します。"
  exit 1
fi

read "depth?深さ [2]: "
depth=${depth:-2}

read "max?最大ページ数 [30]: "
max=${max:-30}

echo ""
echo "開始します..."
echo ""

source venv/bin/activate
python src/main.py --url "$url" --depth "$depth" --max-pages "$max" --format md,html

echo ""
echo "完了しました。output/ フォルダを確認してください。"
read "?Enterキーで閉じる..."
