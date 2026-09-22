# A2・A3 白雲 Main / AMS A4 版の差分レビュー

2026-09-22。別実行の Codex native が読み取り確認。**Mainへの割当変更と実出力に未解消の指摘なし。既レビューの初回試作可の判断を引き継ぐ。** GUI操作・送信・プリンタ制御は実施していない。

対象は同ディレクトリの `A2-A3-white-cloud-MAIN-A4-GUI-verified.3mf` と `A2-A3-white-cloud-MAIN-A4-GUI-final.gcode.3mf`。比較元Aux版のSHAが [前回レビュー](../white-aux-file-review.md) の固定値と一致することを先に確認した。

- **形状・配置不変**: verified の2個のmesh XMLとbuild XMLがAux版と完全一致。48 mm A2/A3の白雲各1、姿勢、倍率、配置を保持。旧形状・初層・内部ブリッジを一から測り直していない。
- **設定不変**: Aux verified、Main verified、Main finalのproject settings全項目が一致。X2D 0.4、Textured PEI、0.16 mm（初層0.20）、3壁、15% gyroid、PLA白、公式開始/終了マクロを保持。
- **割当差分**: plate `Manual / filament_maps=2→1`。Main finalは白logical filament 1の`group_id=0`、`nozzle id=0 / extruder_id=1`、`nozzle_sequence=[0]`。Aux用のmaps2/group1/extruder2が残っていない。G-codeは`M620 M`でremapし、`T0 H-1`で論理filamentを選択するため、raw G-code単体で物理AMS A4を保証するとは扱わない。
- **実出力**: 136層、2,932秒（48分52秒）、17.53 g。実押出138,710経路、A2=79,349、A3=57,207、brim=2,154。A2は1〜136層、A3は1〜97層。空層0。初層Z0.20、3,107経路。
- **変更は経路の移動ではない**: G0/G1/G2/G3のモデル内XYZIJ経路146,414件がAux版と順序・feature・layer込みで完全一致。速度F、加速度M204、引き戻し/戻しEにはMain固有の差分あり。E差分3,435件のうち、XY移動しながら正のEを出す造形経路の差分は0。既レビューの境界・ブリッジ位置・実支持0の評価を再利用できる。
- **完全性**: 両ZIPのCRC正常、埋込G-code MD5一致、未展開式0、終了処理と`M73 P100 R0` / `EXECUTABLE_BLOCK_END`あり。編集用verifiedにはG-codeなし、印刷用はfinal.gcode.3mf。

`support_used=true`と実支持0の既知不整合は残る。`used_for_support=false`、Bridge489経路でAux版と同数。前回確認した約17.46 mmの内部橋渡し区間も経路不変で、取付面や露出外面の欠損とは扱わない。**サポート付きと説明せず、実支持0・内部ブリッジありとする。** 実造形、冷却、橋渡し品質の実証済みとはしない。

```text
MAIN-A4-GUI-verified.3mf SHA256
de70e0d9ab45bd75db83cdcaafed290c6cfa8ba6ebaee46a0575d04c337ce519
MAIN-A4-GUI-final.gcode.3mf SHA256
68886954d14c58300199a7a49783e68fa96efaf0e55b1fa2ae0b207362a2aeac
embedded G-code SHA256
6af303a7319d1ca6d03c69723af438a11d1773fe4bbf0fdd882cac001dd76861
```

親報告: 先行橙109/109完了、空PEI映像、AMS A4のBambu PLA Basicジェイドホワイトを実機で確認済み。子による現物・送信画面の確認ではなく、Mainの論理白をA4へ対応させる最終操作は親担当。再委譲・GUI・在庫・Git操作なし。変更は本記録のみ。

記録確定直前の親報告: 送信画面でMain=A4白、Aux空、PEI・0.4/0.4を確認し、白Main-A4を1回送信。実機受信・0/136層の開始準備・ETA14:12を確認した。これは親の実機観測で、子の独立ファイル検証とは区別する。白の物理完成・初層安定の確認はこの時点では含まれない。
