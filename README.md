# 3DP

3Dプリント用モデル、設計コード、造形データ、検証結果と印刷記録をまとめたリポジトリです。

| プロジェクト | 内容 |
|---|---|
| [分子模型](molecular-models/README.md) | 分子模型と接合試験片、MOFモデル |
| [ラミエル](models/ramiel/README.md) | 通常形態・星形のモデルと印刷データ |
| [カービィのアダプター](models/kirby-vacuum-adapter/README.md) | 接続部の試験片とアダプター |
| [524キーホルダー改善版](models/524-keychain/statue-v7/README.md) | 成功した発色を保持し、フックの支持と不要な塔の消費を改善 |
| [Claude / Cloud・Codex・ChatGPT](concepts/claude-codex-20260922/README.md) | キャラクター案、モデル、色別の印刷データ |
| [ラミエルの参考資料](references/ramiel/README.md) | 形態比較と出典 |

最新の印刷対象・条件・確認状況は、各プロジェクトのREADMEと印刷記録を参照してください。過去の試作や比較用データも含むため、ファイル名だけで印刷対象を決めないでください。

## モデル・スライス済みデータの保存先

保管の正本はこの3DPプロジェクト内です。

- 524キーホルダー: [モデルとスライス候補](models/524-keychain/statue-v7/README.md)、[実際に印刷したv6の記録](models/524-keychain/statue-v6/print-run-20260927/)。
- ラミエル: [printing](models/ramiel/printing/)。
- 分子模型: [slicing](molecular-models/slicing/README.md)。
- Claude / Cloud: [モデル・色別データ・印刷記録](concepts/claude-codex-20260922/README.md)。
- Downloadsに残っていたデータ: [37ファイルの保存先一覧と不足分の取込](imports/downloads-20261001/README.md)。

Downloadsは作業コピーの置き場として扱い、編集用3MF/STL、スライス済みG-code/3MF、設定・検証・印刷記録をプロジェクト内で管理します。

## 開発と検証

印刷準備では [品質・材料消費ルール](docs/print-quality.md) と
[G-code監査](tools/quality-audit/README.md) を使います。最終送信ファイルに対して検査し、実物の確認状況を別に記録します。

各プロジェクトの `requirements.txt` とREADMEに従って環境を用意してください。仮想環境、認証情報、ワークスペース直下の一時ログは管理対象外です。端末に依存する実行ファイルは環境変数で指定し、コマンド記録の `${BAMBU_STUDIO_BIN}` は利用環境のBambu Studio実行ファイルへ置き換えます。

2026-09-22に、個別管理していた4プロジェクトの現在の内容をこのリポジトリへ統合しました。旧リポジトリの履歴は作業端末に退避して保持し、このリポジトリは統合時点からの履歴を記録します。

参考画像・外部資料の出典は各資料の記録に記載しています。資料内の作品・ブランド等の権利はそれぞれの権利者に帰属します。
