# X2Dオフラインスライス補助

2026-09-22。主担当から切り出された補助実装。担当範囲は `slicing_support.py`、`tests/test_slicing_support.py`、本記録。形状作成、GUI、プリンター送信、在庫変更、commit、再委譲は行わない。

主担当の最新要件: 5種類を各1個、台座込み48 mm（利用者の4〜5 cm）で制作し、将来の再縮尺用にパラメータ原本を保持。色別に姿勢を決めた部品を別々に造形し、位置合わせ付き接着組立。将来MakerWorld共有の意向はあるが今回は公開しない。この補助は寸法や形状を変更しない。

## 到達点と呼出し

**補助実装とオフラインテスト: PASS。今回の5作品の実STLによるスライス、GUI往復、実機: NOT_RUN。**

```python
from slicing_support import run_slice
report = run_slice(
    ["parts/body.stl", "parts/base.stl"],
    "sliced/white.3mf",
    "white",
    support=False,
)
```

正確なインターフェイス:

```python
run_slice(stl_paths, output_3mf, color_key, support=False,
          *, preset_root=None, bambu_bin=None, timeout=900) -> dict
prepare_settings(directory, color_key, support=False, *, preset_root=None) -> dict
find_preset_root(preset_root=None) -> pathlib.Path
resolve_preset(folder, name, stack=()) -> dict
inspect_3mf(path, *, cli_log='', expected_support=None) -> dict
summarize_gcode(code) -> dict
patch_gui_deltas(path, deltas) -> None
```

`color_key`は`white / black / orange / translucent_blue / gray`。白・黒・橙・灰はBambu PLA Basic、半透明青はBambu PLA Translucentの公式X2D 0.4 mmプリセット。表示色hexは造形物の測色値ではない。`gray`はPLA Basicであり、別在庫のPLA Matteではない。

設定はBambu Studioの既存`system/BBL`を探索。明示パスまたは`BAMBU_PRESET_ROOT`が優先。実行ファイルは`bambu_bin`または`BAMBU_STUDIO_BIN`、未指定ならmacOS標準のBambuStudioアプリ。コードに個人ホームの絶対パスを埋め込んでいない。

`stl_paths`は単位mm、選定した印刷方向、最低Z=0（許容0.01 mm）、閉じた有限メッシュが必要。独立したSTLごとの寸法はXY 250 mm以内、Z 261 mm以内。3 mmブリム込みでベッドへ置けない配置はスライサー/出力検査で失敗する。入力STLの座標は変更しない。

実行argvは`--load-settings machine;process --load-filaments filament --load-filament-ids 1,... --curr-bed-type Textured PEI Plate --ensure-on-bed --arrange 1 --orient 0 --slice 0 --export-3mf ...`。`--allow-rotations`は付けない。論理filament 1は物理AMS A1の割当ではない。毎回privateな`--datadir`を使用し、ユーザーの既存設定へ保存しない。

出力先隣の非公開ディレクトリ`.出力名-slicing-*/`へ設定・入力ハッシュ・argv・CLI全文ログ・検査reportを保存する。ディレクトリ700、設定/記録600。これらは端末固有パスを含むローカル実行証拠であり、将来の公開用素材から除外する。成功時だけ指定3MFを作成し、既存3MFは上書きしない。CLI失敗/時間超過/検証不合格時は証拠を残し、完成出力を作成しない。自動再試行はしない。

返却reportに層数`layer_count`、秒`estimated_seconds`、g`estimated_filament_g`、押出コマンド数`extrusion_moves`、円弧押出数、サポート押出数、層別件数`layers`、特徴別件数`features`、部品ID別の初層/最終層`objects`、警告、SHA256、設定・ログの所在を含む。層座標の描画や支持の詳細判定は主担当の別検査へ引き渡す。

## 採用設定と根拠

- インストール済みBambu Studio CLIヘルプでバージョン`02.08.02.61`と利用する引数を実読取。
- 機種`Bambu Lab X2D 0.4 nozzle`、工程`0.16mm Standard @BBL X2D`。継承とincludeを再帰展開し、X2D固有開始/終了テンプレートを保持。
- 通常0.16 mm、壁3周、15% gyroid、Textured PEI、同層進行、外側ブリム3 mm/隙間0.1 mm、初層30 mm/s、外壁60 mm/s、prime towerなし。
- 支持は既定なし。`support=True`はプレート起点tree(auto)、支持材/界面材とも既定0＝同じ材料。支持経路が無い場合はその事実を警告へ残す。
- Basic密度1.26 g/cm³、PEI初層/通常55℃、ノズル220℃。Translucent密度1.22、PEI初層60℃/通常55℃、ノズル220℃。今回用に温度を独自推定せず、インストール済み公式プリセットから取得。
- 1色・1枚・1材料の出力のみ受理。複数枚へ自動分割された結果、機種違い、密度0、実押出なし、空層、層数矛盾、支持メタデータ矛盾、要求外の支持、設定差異は不合格。
- GUI読込時の標準値への復帰を防ぐため、`different_settings_to_system`を`[process差分, filament_colour, machine差分なし]`として格納。G-codeを含む他のZIPエントリのバイト列は維持する。今回のGUI往復検証は未実施。

参照した既存実績:

- `molecular-models/scripts/slicing_prep.py`: 継承とincludeの展開、公式X2D開始テンプレート/密度の確認。
- `molecular-models/slicing/README.md`、`gui-import-fix.json`: 空の`different_settings_to_system`でGUI設定が戻る事象と修正後の実確認。
- `models/ramiel/printing/star-v4/README.md`、`estimate.json`、`sliced-preview/black-stand.3mf`: 公式単色スライスと実際の見積り/押出データ。
- `molecular-models/scripts/inspect_toolpaths.py`: start/end Customと移動を除外する実経路解析の前例。

## TDDと実データの区別

先に11テストを作成。実装ファイルが未作成のためimportで`FileNotFoundError: .../production-v1/slicing_support.py`となり、`Ran 1 test / FAILED (errors=1)`を観測した。実装後11件成功。その後、失敗時の出力抑止・既存出力保持・Z=0不備を検査する統合fixtureテスト3件を追加し、14件成功。自己レビューで出力作成時の競合による上書き余地を認め、同一ファイルシステムの排他的hard-linkで公開する実装にしてから最終14件を実行した。

実行:

```sh
.venv/bin/python -m unittest discover \
  -s concepts/claude-codex-20260922/production-v1/tests \
  -p test_slicing_support.py -v
```

最終結果`Ran 14 tests in 0.939s / OK`。

検査名（全件ok）:

1. `test_command_preserves_orientation_and_uses_private_datadir`
2. `test_failed_cli_does_not_publish_requested_output`
3. `test_genuine_prior_archive_metadata_and_real_extrusions`
4. `test_gui_delta_patch_leaves_all_other_archive_bytes_identical`
5. `test_inheritance_include_precedence_and_cycle`
6. `test_installed_presets_resolve_templates_density_and_intent`
7. `test_off_bed_geometry_is_rejected_before_cli`
8. `test_parser_excludes_macros_travel_and_retract_and_counts_arcs`
9. `test_rejects_archive_without_real_extrusion`
10. `test_rejects_generic_machine_zero_density_and_multiple_materials`
11. `test_run_slice_missing_input_does_not_launch_cli`
12. `test_run_slice_publishes_validated_fixture_and_keeps_offline_evidence`
13. `test_support_uses_same_material_on_build_plate`
14. `test_warning_parser_keeps_unknown_warning_and_support_context`

既存の実`star-v4/sliced-preview/black-stand.3mf`を読んだ結果:

| 項目 | 実読取 |
|---|---:|
| 層数 | 150 |
| 時間 | 3406秒 |
| 材料 | 16.51 g |
| 押出コマンド | 33,058 |
| うち円弧押出 | 8,112 |
| 支持押出 | 0 |

G-code SHA256: `b0cd06d59e1f93712a908364585bd5e80a0c49ab93e766d85235be8773050867`。3MF SHA256: `9023fd4f969eae77b799ba7eabb771c3e6d023aa368af9bac2f67a070659a223`。元ファイルは変更していない。これは既存星型ラミエルの黒台座の検証であり、新5作品の造形検証ではない。

合成fixtureは、小さいG-code文字列および既存3MFを一時ディレクトリで改変したもの。CLI呼出しの統合テストはmockであり、新モデルの実スライスと扱わない。テスト用の一時STLは単純な箱。プリンターへ接続していない。

## レビューと残る制限

実装担当の自己レビュー: 対象範囲、機種・材料の完全継承、設定反映、単材料の保持、既存出力保護、失敗時の証拠、秘密値/個人ホームパスの非埋込を確認。独立レビューは主担当側へ引き渡す。

CLIの既存警告`Invalid T65279 / T65535`は公式終了マクロに由来した前例があるが、自動的に無害と分類・抑制しない。新しいCLIログのWarning/Error/Invalid/Influence area/floating/cantilever/unsupportedをそのまま保持し、主担当が内容を確認する。初層時間メタデータ0は実時間の根拠にしない。

今回の設定による初回実スライスは未実行。`--datadir`を分離したCLIでの本モデル出力と全設定の一致は主担当の最初の実スライスで確認する。GUI表示/再スライス、配置の全経路範囲、浮遊領域・薄肉・ギャップ・支持除去、部品の実嵌合、接着強度、透明感、実機造形を本補助だけでは証明できない。単色化は多色切替パージを避ける構成だが、開始処理の排出をゼロにするものではない。

## 運用記録

信頼済み環境ファイルから正本を解決し、共通指示、CURRENT-WORKFLOW、cross-agent-instructions、prepare-3d-printスキルを読んだ。既存Vaultの3d-printingコンテキスト、プリンター環境、材料選定、FIL-006〜010を参照。台帳から色/材質の保有を確認したが、残量・予約・乾燥・現在AMS配列や空プレートは推定しない。

親からClaudeの`loggedIn=false`（認証問題、上限ではない）が報告されており、本分担は既存Codexネイティブ能力の明示選択。Claude使用実績、Claudeへの負荷分散、課金API利用とは扱わない。再委譲なし。

Vault全体への広い検索はiCloud配下で結果が返らず、自分の検索プロセスだけ停止し、既知の正本ファイルを限定して読取。ソース実体の読取は成功。補助担当に見える会話は本分担と親の48mm追記に限り、利用者会話の全履歴は受け取っていない。長い指示/Vault読取のツール表示には切詰めがある。本文は判断と観測の記録で、全会話・全ツール出力の完全保存ではない。親担当がこの記録と実装を全体のVault記録に統合する。

## 主担当による実スライスとレビュー追記

実5作品・23部品を最終形状でスライス済み。結果は `ready/slice-reports.json`、`ready/layers-validation.json`、`validation.md` を参照。上のNOT_RUNは補助単体の引渡し時点の記録である。

主担当が実3MFのbuild transformを照合し、`--orient 0`は接地面の自動変更を止めるが、`--arrange 1`では平面内のZ回転が入ることを確認した。橙の3部品はZ0/90/135度の回転を含む。先頭docstringの「平行移動のみ」を訂正。印刷する接地面は維持され、配置の回転は意図に適合する。設定・公式開始終了コード・支持/材料・ファイル失敗時の挙動・パス混入をレビューした。主担当はこの補助の実装者とは別担当。
