# 搬到有顯示卡的電腦跑模型

2026-11-13：回測在這台電腦（只有 CPU）跑到 1,631 / 3,672 次後暫停。程式會自動偵測顯示卡：
有 NVIDIA 顯示卡且裝了 CUDA 版 torch 時用 GPU，否則用 CPU（可用環境變數 `TWST_DEVICE=cpu` 或 `cuda` 強制指定）。

## 要帶過去的東西

資料庫與模型權重不在 GitHub 上（太大），要自己複製（隨身碟或雲端硬碟）：

| 項目 | 位置 | 大小（2026-11-13） |
|---|---|---|
| 資料庫 | `pipeline/data/tw.sqlite` | 約 830 MB |
| 模型權重 | `pipeline/data/hf/` | 約 140 MB |
| 下載快取（可不帶） | `pipeline/data/http_cache/` | 約 250 MB |
| 金鑰設定（可不帶） | `.env` | — |

**先等這台電腦的工作結束再複製**：上櫃回補（`python -m pipeline status` 看不到 `net-tpex` 鎖）完成後，複製整個 `pipeline/data` 資料夾。
複製時這台電腦不要有任何管線程式在跑，否則資料庫可能複製到一半的狀態。

## 在顯示卡電腦上

1. 安裝 Git、[uv](https://docs.astral.sh/uv/)、[GitHub CLI](https://cli.github.com/)（`gh auth login` 登入同一個 GitHub 帳號）。
2. 下載程式碼並放回資料：
   ```powershell
   git clone https://github.com/Kailunkong0720/tw-stock-terminal.git
   # 把帶來的 data 資料夾放到 tw-stock-terminal\pipeline\data
   cd tw-stock-terminal\pipeline
   uv sync
   ```
3. 換成 CUDA 版的 torch（`nvidia-smi` 右上角的 CUDA Version 決定用哪個，例如 12.8 → cu128）：
   ```powershell
   uv pip install --reinstall torch --index-url https://download.pytorch.org/whl/cu128
   uv run --no-sync python -c "import torch; print(torch.cuda.is_available())"   # 要印出 True
   ```
   之後執行管線一律加 `--no-sync`，否則 uv 會把 torch 換回 CPU 版。
4. 繼續回測（只算還沒算的，已完成的 1,631 次不會重做）：
   ```powershell
   uv run --no-sync python -m pipeline backtest
   ```
5. 完成後輸出並發布：
   ```powershell
   uv run --no-sync python -m pipeline export
   uv run --no-sync python -m pipeline publish
   ```

## 注意

- **同一時間只讓一台電腦發布**：發布會覆蓋 GitHub 上的資料分支。換到顯示卡電腦後，這台電腦的自動接續排程（Claude 的 `tw-stock-terminal-resume`）要先停用。
- 之後每季更新請在同一台電腦上做（資料庫在哪台就在哪台更新）；要換回來就再把 `pipeline/data` 複製回來。
- 在 GPU 上可以考慮改用較大的 Kronos-small 或 Kronos-base（CPU 上太慢才選 mini）。但換模型要重跑全部預測與回測，分析說明會自動記錄新的模型與版本。
