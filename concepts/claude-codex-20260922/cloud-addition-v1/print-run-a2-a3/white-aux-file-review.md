# A2・A3 白雲 Auxiliary 版の独立ファイルレビュー

2026-09-22。Codex native の別実行による読み取り確認。**現ファイルで初回試作へ進められる。必須修正となる具体的なファイル欠陥は見つからない。** `support_used=true` は実支持材の生成を表しておらず、**実支持0・内部ブリッジあり**として扱う。これは実印刷成功の確認ではない。

対象:

- `A2-A3-white-cloud-AUX-GUI-final.gcode.3mf`: 実 G-code を含む印刷用成果物。
- `A2-A3-white-cloud-AUX-GUI-verified.3mf`: A2/A3 の実メッシュと設定を含む編集用成果物。G-code は入っていない。

## 補助ノズルと設定

- final の `slice_info.config`: `printer_model_id=N6`、`filament_maps=2`、白 logical filament 1 の `group_id=1`、`nozzle id=1 / extruder_id=2 / diameter=0.4`。
- `filament_sequence.json` は `nozzle_sequence=[1]`。両成果物の plate 設定は `filament_map_mode=Manual`、`filament_maps=2`。両者の project settings は全項目一致。
- 実 G-code の start block は `M620 M ;enable remap`、`M620 S0A H-1 B`、`T0 H-1`、`M621 S0A B` で論理 filament を選択する。物理 Aux を `T1` で直書きしたものではない。補助ノズルの証拠はこの実行コードと archive の mapping の組合せであり、raw G-code 単体の固定割当とは主張しない。`plate_1.json` の `first_extruder=0` だけで Main と判定しない。
- `printer_model=Bambu Lab X2D`、variant 0.4、Textured PEI、通常層 0.16 mm、初層 0.20 mm、壁3、15% gyroid、PLA白・密度1.26 g/cm³、outer brim 3 mm、by layer。tree(auto)・build-plate-only が有効だが、生成支持経路は0。
- `machine_start_gcode` 14,848文字と `machine_end_gcode` 2,534文字は、インストール済み公式 X2D 0.4 preset を継承展開した内容と全文一致。実行部に未展開式なし、終了処理・`M400`/`M18`・`M73 P100 R0`・`EXECUTABLE_BLOCK_END` を確認。G-code MD5とZIP CRC正常。

## 形状・配置・出力経路

- verified 内の A2/A3 cloud 各1のみ。source STL の SHA は現 `output/manifest.json` と一致。GUIが中心原点へ移したメッシュを `source_offset` で復元し、元STLへ照合。最大頂点差は A2=0.000001996 mm、A3=0.000001340 mm、体積比差 <3.22e−9、face数15,312/18,386一致。両方閉形・単体。既存の48 mm組立形状レビューを再利用。
- GUI の配置は Z 軸周りの小角度回転と平行移動だけ。背面接地の印刷姿勢、倍率、Z最低点0を保持。モデルworld bounds: A2 `[101.6402,142.6331,0]`〜`[174.8598,172.2078,21.7516]` mm、A3 `[112.7751,83.7918,0]`〜`[163.7245,118.6331,15.5516]` mm。
- final はメッシュを含まない G-code package だが、object名/ID160,171、plate bbox、設定が verified と整合。A2は1〜136層、A3は1〜97層に毎層押出あり。途中の欠落層・空層なし。
- 全136層、実押出138,710経路。A2本体79,349、A3本体57,207、brim2,154。初層Z0.20 mmに3,107経路。実初層を画像化し、A2の広い連続面とA3の連続したU形面、それぞれのbrimを確認。
- 全層のモデル/brim押出範囲はXY `[100.665,81.961]`〜`[176.019,174.742]` mmで256×256内。G2/G3円弧は約0.15 mm間隔で評価。Customの起動/purge動作をこのモデル範囲判定に含めていない。
- スライサー予測は4,888秒（1時間21分28秒）、17.53 g、初層206.17秒。実消費・purge・冷却・交換・接着時間の保証ではない。

## 実サポート0の影響判断

`support_used=true` と `used_for_support=false` が同居し、実 G-code の `Support`/`Support interface` 押出は0。したがってメタデータ不整合は残るが、G-codeが存在しない支持に依存していると即断する根拠にはならない。標準の strict `inspect_3mf` はこの不整合を拒否する仕様なので、本レビューでは両方の値を保持して実経路を個別確認した。

実 `Bridge` は489経路。最大直線長23.604 mmはA3の第78層Z12.52 mm、XY `[121.876,103.580]`→`[145.416,105.317]`。前層の実押出をその `LINE_WIDTH/2` で広げ、円弧を約0.1 mm間隔で評価したところ、直下に前層押出のない最長連続区間は約17.457 mm。この値はモデルの欠損や空層ではなく、実際に橋渡しで造形する区間である。

当該直線をGUI配置から組立座標へ戻すと、`[-16.6027,-7.6406,32.1722]`→`[6.8675,-7.6406,34.6820]` mm。胴・頭キーの上端28.7882 mmより上にあるため、取付面ではなく雲の前側内部に位置する。直線上25点は全てSTLの内部。そこから造形方向の完成外面まで1.016〜2.443 mmあり、露出する最終外観面でもない。前層とブリッジを重ねた図も視認し、前層上の着地点を持つ内部橋渡しであることを確認した。

現PLA設定の bridge 25 mm/s とこの内部位置から、試作前の強制サポート追加を必須とする根拠はない。橋渡しの垂れ・冷却・実機の材料状態まではファイル検証で確定しないため、初回の物理結果で確認する。サポートが付いているという説明や、嵌合/表面品質の実証済みという説明はしない。

## ファイル固定・範囲

```text
final.gcode.3mf SHA256
d51b0bff1427513c75e4a56f10e765afee7fb48452fc10dfe1bdd308778a1ae6
verified.3mf SHA256
8b609175df1f47a004e6347d2f37e996c6dda1903ac91c865a13a799e19ebb70
final embedded G-code SHA256
dc32b90077683319a2e6b7eef6be74d25344e8f17c6810f8d568c13e92e8ca11
source A2_cloud.stl SHA256
c72d670f6d521598af6dcbbe7f2496f946ba259d7da532039cceca425f02bf8d
source A3_cloud.stl SHA256
8f2eb0d18cff0478b677adde69d0a8796194f28e668090f9e8ef67b9f92d8ecf
```

主担当は送信画面でMain空/Auxiliary Ext白PLA、実機情報でPLA Basicジェイドホワイトを確認したと報告。子はGUI・実機を再確認しておらず、送信・プリンタ制御・在庫操作・再委譲・Git操作なし。旧Main用estimateとレビュー済み橙/黒は対象外。新コード変更なし。本記録のみ追加。

計測過程で、最初のメッシュ比較はGUIによる中心原点への移動を補正しておらずassertで停止。保存されたsource_offsetを適用し、同一形状を正しく比較して完走した。形状不一致の指摘ではない。画像は一時メモリ上で視認し、追加の画像ファイルは保存していない。
