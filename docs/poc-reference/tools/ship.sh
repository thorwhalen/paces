#!/bin/bash
# Rebuild the page, refresh the app dir, repackage the gifs.
set -e
VID=/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad/vid
APP=/Users/thorwhalen/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance
PY=/Users/thorwhalen/.pyenv/versions/3.12.12/envs/p12/bin/python
cd "$VID"
$PY tools/build_page.py
cp media/icon-512.png site/icon.png
cp -f media/*.mp4 media/*.jpg media/*.png media/*.gif site/media/
cp -f site/index.html "$APP/frontend/index.html"
cp -f site/icon.png "$APP/frontend/icon.png"
cp -f media/*.mp4 media/*.jpg media/*.png media/*.gif "$APP/frontend/media/"
echo "--- app dir ---"; du -sh "$APP"; ls "$APP/frontend/media" | wc -l
