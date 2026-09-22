# 形状の出典

- `chatgpt-blossom.svg`: OpenAI公式 `openai/openai-cookbook` 内のロゴSVG。
  - [元ファイル](https://github.com/openai/openai-cookbook/blob/263b2d5b7b63836c4ea30ee9709e65b7a50cbf6f/examples/voice_solutions/realtime_translation_guide/livekit-translation-demo/public/brand/chatgpt-blossom-black.svg)
  - 2026-09-22に取得。外周と7つの穴を抽出し、実メッシュの線と空間を構成。
  - [OpenAIブランド利用条件](https://openai.com/brand/)。ロゴの改変・商品化等の条件は別途適用される。リポジトリのコードライセンスをブランドの包括許諾とは扱わない。
- Codex: 親フォルダ `references/codex-app-light.png`。導入済みCodexアプリのアイコンから外周と白い記号を抽出。
- Claude: 親フォルダ `references/clawd-sticker-reference.png`、コンセプト `images/b-desk-companions.png`。橙の丸みのある胴体、黒い2つの目、4本足を手作業で設計。
- D1–D4: 親フォルダ `images/d1-d4-chatgpt-companions.png`。選定済みの配置と可愛さを参照。生成画像内のロゴは厳密な製作図として採用していない。

有料の3D生成サービス、外部へのモデルアップロードは使用していない。単純な輪郭・丸い面と接合寸法を直接制御できるため、Manifold CADを選択。Blender工程と三面図からの生成サービス工程はNOT_RUN、実CADの三面と斜視を検査した。
