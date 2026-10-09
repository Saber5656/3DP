# Wood像の参照原本

2026-09-22に実機送信した小型像の大版原本。body-review-only.stl は台座と点を加える前の本体で、150×85×153mm、Z15〜168mm。今回はZを-15移動し、全軸に40/153を掛けて本体として再利用。

build_statue.py は原本の保存用で、元ディレクトリを前提とするためこの場所では直接実行しない。再生成手順の入口は../../build.py、表面フィールドの再利用は../../wood_body.py。外形は保存STLを直接使う。

原本SHA256: build_statue.py 4f779d8d448dca2c01e87136304931c0f832a943d8ff3a5b49e7ae62825d5590、editable-outlines.json d050bb66ccf1b8c760f86a981063b03204950cb39549dce5ddbea47cc4180f06、body-review-only.stl 4274a3d2ce274bab92e59317f1ec3dbf8306b1d3abb7679c896d120f1b531ad7。
