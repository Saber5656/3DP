# 訂正後6種類の単色バッチ準備

2026-09-22。担当範囲は`prepare_corrected_batch.py`、`tests/test_corrected_batch.py`、本記録の3ファイル。既存`production-v1`のコード・造形データ・旧ZIPは変更しない。形状実装、実スライス、final/readyへの公開、GUI、プリンター送信、在庫操作、commit、再委譲は主担当へ戻す。

## 要件と現在の状態

ユーザー訂正は**A1・A2・A3・A4・B4・D3を各1個**。旧D1/D2/D4を今回のバッチに含めない。旧`production-v1`のD1〜D4/B4全成果物と`claude-codex-48mm.zip`を保持し、新A1〜A4を追加する。台座等を含む今回の高さは48 mm。

主担当からの部品構成: A1〜A4は各4部品（橙body、白cloud、黒eye2個）。既存B4は7部品、D3は5部品。計28部品、**白7・橙6・黒14・半透明青1**。灰なし。新cloudも背面接地、`support_recommended=True`。色の割当は入力manifestから取得し、材料別支持フラグは各部品のOR。

**補助コード/TDD/自己レビュー: PASS。新Aモデルの実スライス・実機: NOT_RUN。** 本担当でBambu CLIを実行していない。主担当の新モデル最終化後に以下の入口を実行する。

## APIと実行入口

```python
build_batch_plan(new_manifest, old_manifest) -> dict
prepare_batch(new_manifest=None, old_manifest=None,
              *, execute=False, slice_runner=None) -> dict
verify_preserved_files(preserved_file) -> dict
snapshot_paths(paths) -> dict
verify_preserved(snapshot) -> dict
```

引数なしの既定入力:

- 新: `cloud-addition-v1/output/manifest.json`
- 旧: `production-v1/output/manifest.json`
- 追加前保全一覧: `cloud-addition-v1/preserved-files.json`
- 保持対象の旧ZIP: `claude-codex-48mm.zip`

CLI既定は計画のみ:

```sh
PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BIN" \
  cloud-addition-v1/prepare_corrected_batch.py
```

新モデル最終化後に主担当が実スライスを明示する場合:

```sh
PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BIN" \
  cloud-addition-v1/prepare_corrected_batch.py --slice
```

上の作業ディレクトリは`claude-codex-20260922`。`PYTHON_BIN`は既存の3DP Python環境を指す。CLIを今回の担当が実行したという記録ではない。

`slice_runner`はテスト用の依存注入。通常は指定せず、既存`production-v1/slicing_support.py`の`run_slice`を直接読込する。ソースからcompileして読込するため、旧ツリーに新しいbytecodeを作らない。元helperは変更しない。X2D 0.4 mm / Textured PEI / 0.16 mm設定や個別3MF検査は同helperへ委任。

物理AMS/Extの割当はしない。主担当から「白は別524ジョブで補助Extへロード済み」という新しいVault情報が共有されている。これは今回の4色プレートへの固定割当の根拠にせず、`physical_slot_binding=NOT_SET`を維持する。

## 検証と出力

入力両manifestについて以下を検証する:

- 単位mm、manifestの高さ48、各modelの高さ48、各model/partの数量1。
- model IDと`selected_ids`の一致、model/part ID重複なし、partのdesign整合、実部品数と宣言数の一致。
- 新modelはA1〜A4だけ、旧manifestからはB4/D3だけを選択。
- 固定の期待部品数（A各4/B4=7/D3=5）、色別期待数（白7/橙6/黒14/青1）。
- STLは各入力プロジェクト内の相対パス、存在、`.stl`、SHA256一致。別IDで同じSTLパスを二重登録することは拒否。
- **異なるSTLの内容hashが同じことは許可**。左右の同形の目を1個へまとめず、別部品として各1個印刷するため。
- `support_recommended`はboolean必須。文字列`"false"`を真として誤解しない。
- 計画と実行の間・各色の間・最終結果確定前にもmanifest/STL hashを再確認し、更新途中のモデルを混ぜない。

既定の`cloud-addition-v1/slice-work/corrected/`へprivate保存:

- `batch-plan.json`: 元STLの参照、各色の部品一覧と支持条件。STLを複製しない。
- `preservation-before.json`: 最初のバッチ開始時の旧ツリー/ZIPの保全基準。既存基準を上書きしない。
- `batch-status.json`: 計画/実スライス/失敗、各色の実結果、保全確認。
- `white.3mf / orange.3mf / black.3mf / translucent_blue.3mf`: `--slice`時のみ。各helper実行のprivate設定/ログは同じ階層に作られる。

作業ディレクトリ700、JSONは600。内容に端末固有の絶対パスがあるため、これらは公開用の配布物ではない。final/readyへのコピーや公開可否は主担当が実結果を確認して扱う。既存出力3MFが1個でもあれば全色の再実行前に停止し、完成品を上書きしない。途中失敗の3MF/ログはprivate領域に残る。自動削除/再試行/継続はしない。

## 旧データの不変確認

最初に、主担当が**追加開始前**に保存した`preserved-files.json`の118項目を検証する。単に今回の実行開始時を新基準にして、既に変更された旧データを受理しない。基準一覧のファイル内容・追加/欠落も照合する。親の一覧と同じ除外は`__pycache__`と`slice-work`だけ。

さらに各バッチの開始時から終了時まで、旧`production-v1`ツリー全体（hidden/cache/private slice-workも含む）と旧ZIPをsnapshotし、追加/削除/変更を検知する。この実行中の保全は追加前の成果物一覧より厳密。子のhelperは旧ツリーへbytecodeを作らず、スライサーの作業領域も新フォルダへ分離する。追加前一覧そのもののhashも保持し、途中で基準が書き換わることを拒否する。

失敗時も旧データ保全を確認してstatusへ残す。CLI失敗に加えて旧データ変更が観測された場合、両方の理由をstatusへ保存し、保全エラーを返す。既存の保全基準を自動更新して続行しない。

実データで読み取り確認した結果:

- 追加前の118ファイル: **UNCHANGED**。
- 既存helperをソース読込した後も118ファイル: **UNCHANGED**。
- 観測したhelper署名: `run_slice(stl_paths, output_3mf, color_key, support=False, *, preset_root=None, bambu_bin=None, timeout=900)`。
- `preserved-files.json` SHA256: `78198eeab2d1e8e1ca23b5894731cfa86c5f03558eca211c691b81944d18a266`。

この確認は旧データの読み取りとhelperの関数読込だけで、スライス・GUI・プリンター通信は行っていない。

## TDDの経過

1. 先に12テストを追加し、未作成`prepare_corrected_batch.py`のimportで`FileNotFoundError`となる赤を確認（`Ran 1 test / FAILED (errors=1)`）。
2. 初版実装後12件成功。
3. 主担当から追加前の保全一覧が共有されたため、その一覧を開始前に検証する2テストを先に追加。新しい関数未実装の`AttributeError`、開始前に変更された旧ZIPを拒否しない`AssertionError`という意図した赤を確認（14件中1 failure/1 error）。実装後14件成功。
4. 自己レビューで、許可済み4色間の誤割当でも期待色数が変わること、別プロジェクトの旧manifestを混ぜられることに気付いた。該当テストを先に強化/追加し、16件中2 failureを確認。色別期待数とsibling制約を追加し、16件成功。併せて色間で新STLが変更された場合に次の色へ進まないテストも成功。

最終実行:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover \
  -s concepts/claude-codex-20260922/cloud-addition-v1/tests \
  -p test_corrected_batch.py -v
```

3DP作業ディレクトリで実行。結果`Ran 16 tests in 0.202s / OK`。

全16件:

- `test_exact_six_designs_28_parts_and_four_colors`
- `test_failures_retain_status_and_detect_old_data_mutation`
- `test_historical_baseline_is_checked_before_first_batch`
- `test_old_tree_and_zip_snapshot_detect_changed_added_removed`
- `test_parent_baseline_checks_artifacts_and_excludes_only_declared_transients`
- `test_plan_only_never_loads_or_calls_slicer`
- `test_rejects_duplicate_ids_and_duplicate_paths`
- `test_rejects_legacy_manifest_from_a_different_project`
- `test_rejects_missing_design_and_extraneous_new_design`
- `test_rejects_missing_part_even_if_declared_count_altered`
- `test_rejects_stl_path_escape_and_bad_support_flag`
- `test_rejects_tampered_stl`
- `test_rejects_wrong_quantity_color_or_height`
- `test_rerun_does_not_replace_old_baseline_after_modification`
- `test_slice_is_explicit_groups_by_color_and_preserves_old_data`
- `test_source_change_between_color_plates_stops_batch`

テストのSTL/ZIPは明示された合成bytesで、造形データではない。スライサー呼出しはfake関数。実3Dメッシュ/CLI/機器の成功に読み替えない。機能検査は選択・整合性・保全・失敗時の挙動を対象とする。

## 自己レビュー・限界・引継ぎ

自己レビューは今回の目的、48 mm混在防止、旧D1/D2/D4除外、左右同形部品の数量、原本への非書込、hash基準の継続、色別支持OR、既定が計画だけであること、失敗時の状態記録を対象にした。採用修正後は上記16テストが通った。独立レビューと最終実スライスは主担当へ引き渡す。

X2Dの現物ノズル・プレート・AMS/Extの現状態をこの担当は確認していない。母体helperの1色1プレート制約を維持するため、7個の白部品等が1枚に収まらない場合は自動的に多枚数へ変更せず検査で止まる。必要な分割判断・層の支持除去検査・最終GUI確認は主担当が行う。材料残量や予約を変更していない。

既定の構成は今回の28部品に固定している。形状設計変更で部品を分割/追加する場合、期待数とテストも明示的に更新する。任意の別案件に万能なバッチツールとして扱わない。

環境は既存の正本環境ファイルから解決。共通指示/CURRENT-WORKFLOW/prepare-3d-printの継続方針に従う。Claude認証は前回falseで解消情報なしと親から通知されたため、指定済みCodexネイティブ能力で本分担を継続。Claude利用・上限代替・課金API利用という記録はしない。再委譲なし。

このノートは補助担当に提供された依頼・親の追加情報、判断・TDD・観測・制限を記録したもの。親の利用者会話全文は受け取っていない。元ツール出力を全量保存した記録ではない。主担当が最終モデル/スライス結果とともに既存Vaultへ統合する。


## 主担当の最終実行

上の未実行は補助担当の引継ぎ時点。主担当が実28部品を4色へスライスし、旧118成果物/実行時201ファイルの不変、全28部品の接地・層連続性・ベッド内経路を確認。新しいA3メッシュの退化面修正後、入力変更が白のA3_cloudだけであることをhashで確かめ、白だけ再スライスし、他3色を再利用した。詳細はvalidation.mdとready/selection.json。実機送信は未実施。
