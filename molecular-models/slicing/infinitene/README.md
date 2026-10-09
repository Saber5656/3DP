# インフィニテン / 黒PLAの印刷

2026-09-25。利用者の「プリントして」を受け、インフィニテン1個をX2D「3DP-20P-483」へ送信。プリンターが今回のジョブを受信し、**1/326層・3%の造形開始を確認した。** 最終観測時のノズル220℃・ベッド55℃、残り約2時間58分、完了予測22:52。完成・初層の密着品質・支持除去は未確認。その後、初層開始前にプレート未検出 `0500-8061` で停止した。その後、警告表示が消えてフィラメントロードへ進んだことを確認した。エージェントは警告無視・再開を操作しておらず、再開の契機は未観測。位置確認の依頼はその進行により不要となった。初層と完成の確認状況は [print-run.json](print-run.json) を参照する。受信確認済みなので重複送信しない。

| 項目 | 設定・確認 |
|---|---|
| 模型 | 元のインフィニテンSTLを保持、140 × 89.632 × 52.258 mm、炭素骨格、水素省略 |
| 機種 | Bambu Lab X2D、Main 0.4 mm、標準流量。補助ノズルは使わない |
| 材料 | Bambu PLA Basic Black、AMS A1。実機の素材詳細画面で照合 |
| プレート | Textured PEI、送信前のライブ映像で前の印刷物がないことを確認 |
| 積層 | 0.16 mm、初層0.20 mm、壁3周、充填20% |
| 支持 | Tree(auto)/organic、ビルドプレートのみ、閾値35°、接触面2層、上下Z隙間0.20 mm、XY隙間0.35 mm |
| 接地設定 | 外側ブリム6 mm、隙間0.10 mm。実経路では広いツリー支持の初層が接地を補う |
| 速度 | 初層30、外壁60、内壁100、支持80、接触面50 mm/s |
| 温度 | ノズル220℃、PEI 55℃、公式X2D/PLA設定を使用 |
| 見積り | 3時間4分8秒、33.19 g、326層。模型16.20 g、支持16.99 g。実消費ではない |
| 送信 | ベッドレベリングOn、動的流量校正Auto、ノズルオフセット校正Off、タイムラプスOff |

## 使用ファイル

- [GUI確認済みプロジェクト](ready/infinitene-black-X2D-GUI-verified.3mf)：形状と設定。再印刷時は現在の機器状態を照合しスライスする。
- [GUI最終G-code 3MF](ready/infinitene-black-X2D-GUI-final.gcode.3mf)：今回送信したGUIスライスの経路を書き出したもの。
- [スライス・GUI再読込検証](slice-validation.json)：33項目の設定一致、温度、寸法、経路範囲、ハッシュ。
- [準備条件](preparation.json)、[送信と実機状態](print-run.json)、[レビュー](review.md)。
- [層プレビュー](layer-preview.png)：CLI生成G-codeの押出経路。本体と支持を色分けした図で、実物の配色は黒一色。

元STLの恒久的な切断、拡大縮小、台座追加はしていない。ツリー支持は完成後に取り除く。リングの内外へ工具を入れられる枝状の支持を選んだが、薄い結合棒を支えながら少しずつ除去する必要がある。支持除去後の形状保持・実強度は未検証。

## 検証と復旧

既存の閉じた一体STL検査を再利用し、今回の包装を再読込して元形状の寸法と一致を確認。公式プリセットを現在の導入環境から継承/includeまで展開した。機種固有の開始終了テンプレートは改変していない。

CLIからの相対パス書出しが失敗したため、明示的な `--outputdir` とファイル名に分けて復旧。成功版の実G-codeから支持・326層・256 mm角内の押出経路を確認。元のCLIエラー版は送信していない。

CLIの空の差分メタデータでGUI読込時に設定が戻る既知問題に対応し、`different_settings_to_system` に今回の変更キーを記録してから開いた。GUI再スライスでも3時間4分8秒/33.19 g/326層。GUI保存プロジェクトとCLIの33項目が一致し、GUI最終経路を別ファイルへ保存した。

`Invalid T65279 / T65535` は公式終了テンプレートのAMS退避マクロ由来のCLIパーサー警告。前回と同様に元の公式G-codeを保持した。CLIの初層時間0は実時間の根拠にしていない。

今回の変更は既存メッシュ・既存検査関数を使った設定と成果物の追加であり、新規の実行コード変更はないためTDD対象外。実モデルの再読込、設定値のassert、実G-code検査、GUI照合を実施した。在庫残量はスライサー見積りから減算していない。

## 再現

`BAMBU_STUDIO_BIN` は導入済みBambu Studioの実行ファイルを指定する。`presets/` は今回使用した公式設定の展開済み複製。CLIから直接送信せずGUI読込と実機照合を行う。

```sh
mkdir -p slicing/infinitene/provisional
"$BAMBU_STUDIO_BIN" --debug 2 \
  --load-settings 'slicing/infinitene/presets/machine.json;slicing/infinitene/presets/process.json' \
  --load-filaments slicing/infinitene/presets/filament.json \
  --curr-bed-type 'Textured PEI Plate' --ensure-on-bed --arrange 1 --orient 0 \
  --slice 0 --outputdir "$PWD/slicing/infinitene/provisional" \
  --export-3mf infinitene-black-X2D-04-PEI.3mf output/infinitene.stl
```

再生成時のGUI用差分キーは `slice-validation.json` の `diff_keys` を参照。今回の起動操作・原依頼・取得可能な公開ログ・実行ログ・成果物は既存Agents Vaultの `01-Projects/3d-printing/計画/molecular-models/infinitene-print-20260925/` に保存する。

送信後の経過は、プレート検出停止 → 警告表示消失 → 材料ロード → ノズル清掃 → 自動ベッドレベリング → 初層造形。最終映像では金色のTextured PEI面を確認した。最初の映像だけでは取り外し式プレートの着座を確定できなかったため、その確認範囲を準備記録へ明記した。
