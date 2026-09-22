# ラミエル：通常形態 v4・星型 v6

**星型v6は中央を5方向へ開く星形の凹みに修正し、CAD検証と試算用スライスまで完了。星型は未送信です。** 通常形態の造形成功は利用者から別途報告されています。

| 形態 | 大きさ | 本体・組立 |
|---|---|---|
| 通常v4 | 上下100 mm、台座込み112 mm | 青い一体中空本体＋黒い受け台 |
| 星型v6 | 幅150 mm、前後奥行67.88 mm、街込み高さ145.68 mm | 青い一体中空本体＋黒い街の台座＋3 mm赤ビーズ |

両方とも内部格子・中央の管・本体の接合ピンはありません。公称壁厚1.2 mm。星型の寸法は写真を基にした設計値で、公式実測ではありません。

## 星型 v6

[設計・写真との対応・量と時間・検証の詳細](printing/star-v6/README.md)

![再設計した星型](printing/star-v6/star-design.png)

中央の小さな五角形の穴をなくし、10枚の斜面と5本の深いV字の谷を実際の形状へ作り込みました。[修正前後の比較](printing/star-v6/core-comparison.png)。

5本の先端をコアの前面より約35 mm前へ出し、四角い根元を持つ立体へ作り直しました。後方の尖りは主5本の裏側へ短く集約。台座は街の建物の屋根を下面に沿わせ、先端を避けて複数の広い斜面で支える形です。

[横からの前後関係・根元4点・台座の支持範囲](printing/star-v6/design-checks.png) / [中央断面](printing/star-v6/centre-detail.png)

市販赤ビーズの後付けを想定し、赤フィラメントとLEDは使いません。球の周りの凹面まで写真の赤色へ寄せる場合は後塗りが必要です。青65.87 g＋黒120.27 g＝**186.14 g・約11時間35分**の2プレート試算。街の台座にした分、黒の使用量は旧3点受けから増えています。GUI最終割当・星型の実機造形・台座の実適合は未確認です。

## 通常形態 v4

[送信と実機の記録](printing/default-v4-onepiece/PRINT-RUN.md) / [印刷設定と成果物](printing/default-v4-onepiece/README.md)

一体中空の正八面体で、辺を下にして外側をサポートする姿勢。X2Dメインノズル、黒A1の台座→青A2の本体という部品順で送信済み。青33.64 g＋黒13.11 g＝46.75 g、3時間42分32秒の最終見積り。別途の記録で、2026-09-22に利用者から造形成功の報告を受けています。通常のSTL・GLB・3MF・送信データは変更していません。

## 形状データ

- [通常本体STL](output/stl/default_body.stl) / [通常台座STL](output/stl/default_cradle.stl)
- [星本体STL](output/stl/star_body.stl) / [星台座STL](output/stl/star_base.stl)
- 完成姿勢：[通常3MF](output/default-display-assembly.3mf) / [星3MF](output/star-display-assembly.3mf)。形状データで、プリンター・材料・造形設定は含みません。
- 3Dプレビュー：[通常GLB](output/default-preview.glb) / [星GLB](output/star-preview.glb)。GLBはm・Y軸上向き、STL/3MFはmm。
- [外観](output/preview.png) / [無地の形状レビュー](output/solid-review.png) / [メッシュ検証値](output/mesh-report.json)

現行STLは10種類。通常2・星2の標準4部品と、ビーズ受け・星の先端・通常の先端・厚み0.8/1.2/1.6 mmの板の試験片6種類です。ビーズは市販品の表示用形状として組立プレビューにだけ含みます。

## 再生成・検証

Python 3.12と[依存ライブラリ](requirements.txt)を用います。

```sh
python -m unittest discover -s tests -v
python build.py
python render.py
python scripts/render_star_checks.py
python scripts/render_core_comparison.py
```

[設計寸法](design.json) / [CAD生成](build.py) / [工程記録](JOB-RECORD.md) / [基準の5写真](references/figure-photos/README.md) / [背面調整の追加写真](references/compact-rear/README.md)。画像は実CADの不透明表示で、透過・発光のシミュレーションではありません。旧星型[v4](printing/star-v4/README.md)・[v2](printing/star-v2/README.md)・[v3](printing/star-v3/README.md)の説明・試算は履歴として保持しています。
