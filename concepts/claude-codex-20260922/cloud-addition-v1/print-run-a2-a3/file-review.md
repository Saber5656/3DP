# A2・A3 橙胴／黒目 3MF の送信前ファイルレビュー

2026-09-22。親と別の Codex native 実行で読み取り確認。**対象 2 ファイルに未解消の指摘なし。** 実機への送信・GUI の材料割当・実印刷は本レビューで実行していない。白 `ESTIMATE-main-only` は補助ノズル用の送信準備済みデータではなく、レビュー・送信判定の対象外。

| 対象 | 部品 | 層数 | 実押出経路数 | 支持押出数 | スライサー予測 |
|---|---|---:|---:|---:|---|
| `A2-A3-orange-body.3mf` | A2 胴×1、A3 胴×1 | 109 | 79,758 | 6,539 | 43分44秒、12.67 g |
| `A2-A3-black-eyes.3mf` | A2 左右目、A3 左右目の計4個 | 10 | 1,537 | 0 | 6分30秒、0.13 g |

## 根拠

- `output/manifest.json` の該当 6 STL の SHA-256 を実ファイルと `evidence/source-estimate.json` に照合し、全件一致。3MF の object 名・件数を照合し、内部メッシュを component transform で復元して STL と比較。頂点の相互最近傍差は最大 0.000001014 mm、face 数一致、体積比差は最大 4.20e−9。対象外の雲や他デザインなし。
- 両方とも `printer_model=Bambu Lab X2D`、variant 0.4、主ノズル 0.4、Textured PEI、通常層 0.16 mm、初層 0.20 mm、壁3、15% gyroid、PLA 密度 1.26 g/cm³。橙は tree(auto)・build-plate-only 支持、黒は支持なし。両方 outer brim 3 mm。黒は小部品のため sparse infill の実経路はなく、壁と solid infill が占める。
- 埋込 6 メッシュは閉形、Z 最低点=0、prescribed back orientation を保持。plate は 256×256 mm、全て範囲内。橙の2胴は Y 方向に約24 mmの空き。黒4目は約2 mm以上の部品間隔があり、近接部の brim は結合するが部品本体は離れている。
- 実 G-code の第1層を画像化して視認。橙2胴の面と周囲の支持の足、黒4目の面と brim を確認。全オブジェクトが第1層から押出し、空層なし。初層は橙1,232経路（支持467）、黒739経路。橙支持は第1〜55層の全55層に実経路があり、support interface 218経路を含む。support metadata と実押出が一致。
- モデル/支持/brim の全層押出 XY 範囲は、橙 `[115.44596,80.17521]`〜`[161.05764,166.729]` mm、黒 `[130.728,120.774]`〜`[145.786,135.205]` mm。G2/G3 は円弧として約0.2 mm間隔に評価。起動時の purge、Custom motion はこの範囲評価から除外。
- project settings の `machine_start_gcode` 14,848文字・`machine_end_gcode` 2,534文字は、インストール済み公式 X2D 0.4 preset を継承展開した値と全文一致。実 G-code に X2D start block、加熱・初期化処理、finish block、hotend 停止、M400/M18、`M73 P100 R0`、`EXECUTABLE_BLOCK_END` がある。実行部に未展開の `{...}` / `[...]` 式なし。G-code MD5 は archive 内値と一致、ZIP CRC正常。
- archive 内警告なし。元 CLI の標準出力ログはこのディレクトリに含まれず、過去の CLI 警告全件の再照合はしていない。`Floating vertical shell` は G-code の feature 名として5,069経路あるが、単独で浮遊部品警告とは解釈していない。

## 対象の固定

```text
A2-A3-orange-body.3mf
  package SHA256 c19defcf59177cfc557a3ede555366953a5519e0d02bc8b72402b536f0422212
  G-code SHA256  dff42fda89d4d187fcc86d9600fe8e585689a61f71dc9b4f6926a8a264a82645
A2-A3-black-eyes.3mf
  package SHA256 792083f7a29efc4546344a1e5b176e44944f33e718d147843fcbbf9f51d3b558
  G-code SHA256  c0d2cb8e8b5d7e2c7521f200d0272127157dc9cbb0895c38689be7c1e5336677
```

48 mm は完成組立の高さであり、寝かせた個別パーツの Z 高さではない。未変更形状は `../geometry-review.md` の確認結果を再利用した。本レビューは数値と選択箇所の経路確認であり、全面の支持除去性、押出線の隙間・重なり、機械の動作、物理的成功の保証ではない。時間/重量はスライサー値で、実 startup/purge、冷却、交換、接着時間を保証しない。

3MF の単一論理 filament を物理 AMS A4 と同一視していない。橙 AMS A4 と白 auxiliary Ext の現物確認・送信画面での割当は親の担当。黒の実物材料割当も送信時に親が確認する。ファイル以外の状態を子が観測したとは扱わない。GUI/プリンタ制御/在庫操作/外部公開/再委譲/Git操作なし。TDD対象となるコード変更なし。本記録のみ追加。
