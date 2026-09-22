# A2・A3 黒目 GUI 最終版の差分レビュー

2026-09-22。Codex nativeの別実行で読み取り確認。**今回のGUI最終版に未解消の指摘なし。前回の初回試作可の判定を引き継げる。** 黒の送信は行っていない。

対象は同ディレクトリの `A2-A3-black-eyes-MAIN-A1-GUI-verified.3mf` と `A2-A3-black-eyes-MAIN-A1-GUI-final.gcode.3mf`。比較元 `../A2-A3-black-eyes.3mf` のSHAは前回 [file-review.md](../file-review.md) と一致（`792083f7a29efc4546344a1e5b176e44944f33e718d147843fcbbf9f51d3b558`）。

- **4個の形状不変**: A2左右目、A3左右目の4 mesh XMLが比較元と完全一致。GUIの中心原点補正を含むcomponent/build transformを適用すると、実配置の最大頂点差は1.273e−7 mm。全4個とも同じ接地Z=0、倍率・向き・配置を保持。未変更形状の肉厚等は前回レビューを再利用。
- **設定差に造形条件変更なし**: verifiedとfinalのproject settingsは全項目一致。比較元との差はpreset名称/継承・GUI差分記録、AMS情報、host情報、色メタ、無効なwipe towerのY座標など。`filament_flush_temp_fast`はゼロ配列の長さだけ変わる。X2D 0.4、Textured PEI、通常層0.16 mm・初層0.20 mm、3壁、15% gyroid、黒PLA、brim3 mm、support無効、公式start/endマクロの値は不変。
- **Main割当**: plate maps1、黒logical filament1のgroup0、nozzle id0 / extruder_id1、nozzle_sequence=[0]。物理AMS A1はraw G-codeで固定保証するものではなく、送信時の親による割当確認と合わせる。
- **実出力**: 4オブジェクト、10層、390秒（6分30秒）、0.13 g。A2目2個は第1〜10層、A3目2個は第1〜9層。空層0、支持0、archive内警告0。
- **重大な経路変化なし**: 実押出1,537→1,540経路（A2各+1、brim+1）。物体名・層ごとの全39組（38個別層+brim初層）を、直線/円弧とも約0.02 mm間隔で比較。相互最近傍の最大経路差は約0.02804 mm。丸めだけで完全同一とは扱わないが、0.4 mmノズルに対する小さな局所差で、部品消失・移動・層欠落の変化なし。全実押出XY範囲は `[130.728,120.774]`〜`[145.786,135.205]` mmで比較元と同じ。既レビューの初層・brim・4個の分離を維持。
- **完全性**: 両ZIPのCRC正常、最終G-codeのMD5一致、未展開式0、終了処理と`EXECUTABLE_BLOCK_END`あり。verifiedは編集用、G-codeを含む印刷用はfinal.gcode.3mf。

```text
verified.3mf SHA256
11258804f015214510091a4a70d44870bf2887b6bc74c6a0a1afed03f88a3f2f
final.gcode.3mf SHA256
7fb3655e350a99f301e454456d65f0004b71a1d9f958e3ca736ebfcd74f21242
embedded G-code SHA256
c59b63fff1fbc0061e0881abb1c73c36a38469678a73acf8dc464e5274de7a3f
```

親報告ではGUI送信previewでMain=A1、補助空、liveでA1=Bambu PLA Basicブラックを確認済み。白が印刷準備中のため黒は未送信。子は実機を操作/観測せず、GUI・送信・Git・再委譲なし。物理印刷成功の証明ではなく、ファイル差分の確認。本記録のみ追加。
