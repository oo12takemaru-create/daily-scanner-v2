"""
╔══════════════════════════════════════════════════════════════════╗
║   🎯 デイリースキャナー v2.0 (Kawamura Custom Edition)           ║
║   🛡 サーキットブレーカー搭載 - 暴落時は自動で停止警告           ║
╚══════════════════════════════════════════════════════════════════╝

【v1.0からの改善点】
  ・サーキットブレーカー搭載（VIX>35、日経-15%、5連敗で警告）
  ・暴落時は「HALT」表示でエントリー回避を推奨
  ・連敗履歴の引き継ぎ機能（前日までの記録を保持）
  ・毎朝の運用判断が一瞬でできるダッシュボード化

【毎朝のルーティン】
  8:30頃（寄付き前）:
    1. このスクリプトを実行
    2. 相場環境（NORMAL/HALT）を確認
    3. NORMALならシグナル確認→SBI証券で指値注文
    4. HALTなら今日は見送り、休む

【実行コマンド】
  python daily_scanner_v2.py                           # 基本実行
  python daily_scanner_v2.py --notify line             # LINE通知付き
  python daily_scanner_v2.py --notify discord          # Discord通知付き
  python daily_scanner_v2.py --capital 500000          # 資金50万円で計算
  python daily_scanner_v2.py --current-positions 3     # 既に3銘柄保有中

【連敗HALT機能について】
  過去のトレードの連敗情報はCSVに保存され、翌日以降も引き継がれます。
  連敗情報ファイル: trade_history.csv
  連敗判定を使わない場合: --no-loss-tracking

【必要な環境変数（通知を使う場合のみ）】
  LINE通知:    LINE_NOTIFY_TOKEN を設定
  Discord通知: DISCORD_WEBHOOK_URL を設定

【インストール】
  pip install yfinance pandas numpy rich requests
"""

import sys, argparse, datetime, os, json, warnings
from collections import defaultdict

def check_libs():
    missing = []
    for lib in ["yfinance", "pandas", "numpy", "rich"]:
        try: __import__(lib)
        except ImportError: missing.append(lib)
    if missing:
        print(f"\n必要なライブラリが不足: {', '.join(missing)}")
        print(f"pip install {' '.join(missing)}\n"); sys.exit(1)

check_libs()
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.rule import Rule
from rich import box

console = Console()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  銘柄リスト（統合バックテスト v2.1 と同じ）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GLOBAL_TICKERS = {
    "^N225":  "日経225",
    "^GSPC":  "S&P500",
    "^VIX":   "VIX恐怖指数",
}

JAPAN_STOCKS = {
    "8035.T": ("東京エレクトロン", "半導体製造装置"),
    "6857.T": ("アドバンテスト", "半導体製造装置"),
    "6146.T": ("ディスコ", "半導体製造装置"),
    "6920.T": ("レーザーテック", "半導体製造装置"),
    "7735.T": ("SCREEN HD", "半導体製造装置"),
    "6728.T": ("アルバック", "半導体製造装置"),
    "6323.T": ("ローツェ", "半導体製造装置"),
    "6758.T": ("ソニー", "電機"),
    "6861.T": ("キーエンス", "FAセンサー"),
    "6273.T": ("SMC", "空圧制御"),
    "6981.T": ("村田製作所", "電子部品"),
    "6762.T": ("TDK", "電子部品"),
    "6971.T": ("京セラ", "電子部品"),
    "6954.T": ("ファナック", "産業用ロボット"),
    "7011.T": ("三菱重工", "重工業"),
    "7012.T": ("川崎重工", "重工業"),
    "7013.T": ("IHI", "重工業"),
    "6301.T": ("コマツ", "建機"),
    "6326.T": ("クボタ", "農機"),
    "6367.T": ("ダイキン", "空調"),
    "6594.T": ("ニデック", "モーター"),
    "6501.T": ("日立製作所", "総合電機"),
    "6503.T": ("三菱電機", "総合電機"),
    "6506.T": ("安川電機", "モーター"),
    "6902.T": ("デンソー", "自動車部品"),
    "7974.T": ("任天堂", "ゲーム"),
    "9684.T": ("スクウェア・エニックス", "ゲーム"),
    "9697.T": ("カプコン", "ゲーム"),
    "9766.T": ("コナミ", "ゲーム"),
    "3659.T": ("ネクソン", "ゲーム"),
    "6460.T": ("セガサミーHD", "ゲーム"),
    "4307.T": ("野村総研", "ITサービス"),
    "4063.T": ("信越化学", "化学"),
    "4568.T": ("第一三共", "医薬品"),
    "4519.T": ("中外製薬", "医薬品"),
    "4523.T": ("エーザイ", "医薬品"),
    "4578.T": ("大塚HD", "医薬品"),
    "2413.T": ("エムスリー", "医療IT"),
    "4751.T": ("サイバーエージェント", "広告IT"),
    "4385.T": ("メルカリ", "フリマEC"),
    "4478.T": ("フリー", "SaaS"),
    "4704.T": ("トレンドマイクロ", "セキュリティ"),
    "9843.T": ("ニトリHD", "小売"),
    "3382.T": ("セブン&アイ", "小売"),
    "9983.T": ("ファーストリテイリング", "小売"),
    "7532.T": ("パンパシHD", "小売"),
    "8227.T": ("しまむら", "小売"),
    "2670.T": ("ABCマート", "小売"),
    "3092.T": ("ZOZO", "ECファッション"),
    "3088.T": ("マツキヨココカラ", "ドラッグ"),
    "9832.T": ("オートバックス", "カー用品"),
    "3048.T": ("ビックカメラ", "家電量販"),
    "9201.T": ("日本航空", "空運"),
    "9202.T": ("ANA", "空運"),
    "9020.T": ("JR東日本", "鉄道"),
    "9021.T": ("JR西日本", "鉄道"),
    "9022.T": ("JR東海", "鉄道"),
    "4661.T": ("オリエンタルランド", "レジャー"),
    "9602.T": ("東宝", "映画"),
    "9432.T": ("NTT", "通信"),
    "9433.T": ("KDDI", "通信"),
    "9434.T": ("ソフトバンク", "通信"),
    "9984.T": ("ソフトバンクG", "投資会社"),
    "8058.T": ("三菱商事", "商社"),
    "8031.T": ("三井物産", "商社"),
    "8001.T": ("伊藤忠商事", "商社"),
    "8002.T": ("丸紅", "商社"),
    "8053.T": ("住友商事", "商社"),
    "2768.T": ("双日", "商社"),
    "7203.T": ("トヨタ自動車", "自動車"),
    "7267.T": ("ホンダ", "自動車"),
    "7201.T": ("日産自動車", "自動車"),
    "7269.T": ("スズキ", "自動車"),
    "7261.T": ("マツダ", "自動車"),
    "7270.T": ("SUBARU", "自動車"),
    "4005.T": ("住友化学", "化学"),
    "4188.T": ("三菱ケミカル", "化学"),
    "4042.T": ("東ソー", "化学"),
    "4452.T": ("花王", "化学"),
    "4901.T": ("富士フイルム", "化学"),
    "3402.T": ("東レ", "化学"),
    "4183.T": ("三井化学", "化学"),
    "4204.T": ("積水化学", "化学"),
    "5019.T": ("出光興産", "石油"),
    "5020.T": ("ENEOS", "石油"),
    "5411.T": ("JFE", "鉄鋼"),
    "5401.T": ("日本製鉄", "鉄鋼"),
    "5713.T": ("住友金属鉱山", "非鉄"),
    "5802.T": ("住友電工", "電線"),
    "2502.T": ("アサヒGHD", "飲料"),
    "2503.T": ("キリンHD", "飲料"),
    "2802.T": ("味の素", "食品"),
    "2914.T": ("JT", "たばこ"),
    "2897.T": ("日清食品HD", "食品"),
    "2801.T": ("キッコーマン", "食品"),
    "2269.T": ("明治HD", "食品"),
    "9101.T": ("日本郵船", "海運"),
    "9104.T": ("商船三井", "海運"),
    "9107.T": ("川崎汽船", "海運"),
    "8802.T": ("三菱地所", "不動産"),
    "8801.T": ("三井不動産", "不動産"),
    "8830.T": ("住友不動産", "不動産"),
    "3003.T": ("ヒューリック", "不動産"),
    "8306.T": ("三菱UFJ", "銀行"),
    "8316.T": ("三井住友FG", "銀行"),
    "8411.T": ("みずほFG", "銀行"),
    "8591.T": ("オリックス", "リース"),
    "8473.T": ("SBIホールディングス", "証券"),
    "8604.T": ("野村HD", "証券"),
    "8766.T": ("東京海上", "保険"),
    "8750.T": ("第一生命HD", "保険"),
    "8267.T": ("イオン", "小売"),
    "8113.T": ("ユニ・チャーム", "日用品"),
    "4502.T": ("武田薬品", "医薬品"),
    "4503.T": ("アステラス製薬", "医薬品"),
    "3436.T": ("SUMCO", "半導体"),
    "6976.T": ("太陽誘電", "電子部品"),
    "6701.T": ("NEC", "電機"),
    "6702.T": ("富士通", "電機"),
    "6098.T": ("リクルートHD", "人材"),
    "4755.T": ("楽天グループ", "IT"),
    "9735.T": ("セコム", "警備"),
    "9064.T": ("ヤマトHD", "物流"),
    "9503.T": ("関西電力", "電力"),
    "9501.T": ("東京電力HD", "電力"),
    "9531.T": ("東京ガス", "ガス"),
    "1605.T": ("INPEX", "石油"),
    "5108.T": ("ブリヂストン", "タイヤ"),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  引数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_args():
    p = argparse.ArgumentParser(description="Daily Signal Scanner v2")
    p.add_argument("--capital", type=float, default=1000000,
                   help="運用資金（デフォルト100万円）")
    p.add_argument("--risk", type=float, default=1.0,
                   help="1トレードリスク（パーセント、デフォルト1.0）")
    p.add_argument("--max-positions", type=int, default=10,
                   help="同時保有上限（デフォルト10銘柄）")
    p.add_argument("--current-positions", type=int, default=0,
                   help="既に保有中のポジション数（残り枠を計算）")
    p.add_argument("--notify", type=str, default=None,
                   choices=["line", "discord"],
                   help="通知先（line=LINE Notify, discord=Webhook）")
    p.add_argument("--save-csv", action="store_true",
                   help="シグナルをCSV保存（後から参照用）")
    # v2: サーキットブレーカー関連
    p.add_argument("--halt-vix", type=float, default=35.0,
                   help="HALT発動VIX閾値（デフォルト35）")
    p.add_argument("--halt-n225-drop", type=float, default=15.0,
                   help="HALT発動する日経1ヶ月下落率（デフォルト15）")
    p.add_argument("--halt-consecutive-losses", type=int, default=5,
                   help="HALT発動連敗数（デフォルト5）")
    p.add_argument("--no-loss-tracking", action="store_true",
                   help="連敗履歴の追跡を無効化")
    p.add_argument("--force-scan", action="store_true",
                   help="HALT状態でもシグナルをスキャン（参考用）")
    return p.parse_args()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  マーケット環境判定（v2.1と同じロジック）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_global_data(start, end):
    data = {}
    for tk in GLOBAL_TICKERS:
        try:
            df = yf.download(tk, start=start, end=end,
                             progress=False, auto_adjust=True)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                data[tk] = df
        except Exception:
            pass
    return data


def detect_market_regime(global_data, date=None):
    if date is None:
        date = datetime.datetime.now()

    signals = {}
    if "^N225" in global_data:
        df = global_data["^N225"]
        df_sub = df[df.index <= date] if date else df
        if len(df_sub) >= 200:
            close = df_sub["Close"].iloc[-1]
            ma200 = df_sub["Close"].rolling(200).mean().iloc[-1]
            ma50 = df_sub["Close"].rolling(50).mean().iloc[-1]
            signals["n225_close"] = close
            signals["n225_ma200"] = ma200
            signals["n225_above_200ma"] = close > ma200
            signals["n225_above_50ma"] = close > ma50
            if len(df_sub) >= 22:
                signals["n225_1m_change"] = (close / df_sub["Close"].iloc[-22] - 1) * 100

    if "^GSPC" in global_data:
        df = global_data["^GSPC"]
        df_sub = df[df.index <= date] if date else df
        if len(df_sub) >= 200:
            close = df_sub["Close"].iloc[-1]
            ma200 = df_sub["Close"].rolling(200).mean().iloc[-1]
            signals["sp500_close"] = close
            signals["sp500_above_200ma"] = close > ma200

    if "^VIX" in global_data:
        df = global_data["^VIX"]
        df_sub = df[df.index <= date] if date else df
        if not df_sub.empty:
            signals["vix"] = df_sub["Close"].iloc[-1]

    vix = signals.get("vix", 20)
    change_1m = signals.get("n225_1m_change", 0)

    if vix > 30 and change_1m < -10:
        regime = "PANIC"
    elif not signals.get("n225_above_200ma", True) or vix > 25:
        regime = "BEARISH"
    elif (signals.get("n225_above_200ma", False) and
          signals.get("n225_above_50ma", False) and
          signals.get("sp500_above_200ma", False) and
          vix < 20 and change_1m > 0):
        regime = "BULLISH"
    else:
        regime = "NEUTRAL"

    return regime, signals


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  v2: サーキットブレーカー判定（HALT-only）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_circuit_breaker(signals_raw, consecutive_losses, config):
    """v2.4と同じロジックで HALT 判定
    Returns: (is_halt, reason, details)
      is_halt: bool
      reason: str
      details: dict (各指標の値)
    """
    halt_vix = config.get("halt_vix", 35.0)
    halt_n225_drop = config.get("halt_n225_drop", 15.0)
    halt_losses = config.get("halt_consecutive_losses", 5)

    details = {
        "vix": signals_raw.get("vix", None),
        "n225_1m_change": signals_raw.get("n225_1m_change", None),
        "consecutive_losses": consecutive_losses,
        "halt_vix_threshold": halt_vix,
        "halt_n225_threshold": halt_n225_drop,
        "halt_losses_threshold": halt_losses,
    }

    # VIX > halt_vix（極度のパニック）
    vix = signals_raw.get("vix")
    if vix is not None and vix > halt_vix:
        return True, f"VIX={vix:.2f} > {halt_vix}（極度のパニック）", details

    # 日経1ヶ月-X%以上下落
    change_1m = signals_raw.get("n225_1m_change")
    if change_1m is not None and change_1m < -halt_n225_drop:
        return True, f"日経1ヶ月{change_1m:+.1f}%（急落）", details

    # 連敗
    if consecutive_losses >= halt_losses:
        return True, f"{consecutive_losses}連敗中（手法不適合期）", details

    return False, None, details


def load_trade_history(history_file="trade_history.csv"):
    """過去のトレード履歴を読み込み、直近の連敗数を取得
    Returns: consecutive_losses (int)
    """
    if not os.path.exists(history_file):
        return 0

    try:
        import csv
        results = []
        with open(history_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pnl = float(row.get("pnl", 0))
                results.append(pnl)

        # 直近から遡って連敗数をカウント
        consecutive = 0
        for pnl in reversed(results):
            if pnl <= 0:
                consecutive += 1
            else:
                break
        return consecutive
    except Exception as e:
        console.print(f"[yellow]トレード履歴読み込みエラー: {e}[/]")
        return 0


def save_trade_result(trade_result, history_file="trade_history.csv"):
    """トレード結果を履歴ファイルに追記
    trade_result: dict {date, ticker, name, pnl, ...}
    """
    try:
        import csv
        file_exists = os.path.exists(history_file)
        with open(history_file, "a", newline="", encoding="utf-8-sig") as f:
            fieldnames = ["date", "ticker", "name", "strategy", "pnl", "pnl_pct", "notes"]
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(trade_result)
        return True
    except Exception as e:
        console.print(f"[yellow]履歴保存エラー: {e}[/]")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  インジケーター準備
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def prepare_indicators(df):
    df = df.copy()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA150"] = df["Close"].rolling(150).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["MA25"] = df["Close"].rolling(25).mean()
    df["BB_mid"] = df["Close"].rolling(20).mean()
    df["BB_std"] = df["Close"].rolling(20).std()
    df["BB_lower"] = df["BB_mid"] - 2 * df["BB_std"]
    df["BB_lower_1_5"] = df["BB_mid"] - 1.5 * df["BB_std"]
    df["Vol20"] = df["Volume"].rolling(20).mean()

    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR20"] = tr.rolling(20).mean()
    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  シグナル検出ロジック（v2.1と同じ）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_trend_template(df, idx):
    """Minervini Trend Template 8/8"""
    if idx < 200:
        return False
    close = df["Close"].iloc[idx]
    ma50 = df["MA50"].iloc[idx]
    ma150 = df["MA150"].iloc[idx]
    ma200 = df["MA200"].iloc[idx]
    if pd.isna(ma50) or pd.isna(ma150) or pd.isna(ma200):
        return False
    if not (close > ma150 and close > ma200):
        return False
    if not (ma150 > ma200):
        return False
    ma200_20ago = df["MA200"].iloc[idx-20] if idx >= 20 else None
    if ma200_20ago is None or pd.isna(ma200_20ago) or not (ma200 > ma200_20ago):
        return False
    if not (ma50 > ma150 > ma200):
        return False
    if not (close > ma50):
        return False
    low_52w = df["Low"].iloc[max(0, idx-252):idx+1].min()
    if not (close >= low_52w * 1.25):
        return False
    high_52w = df["High"].iloc[max(0, idx-252):idx+1].max()
    if not (close >= high_52w * 0.75):
        return False
    if idx >= 126:
        ret_6m = (close / df["Close"].iloc[idx-126] - 1) * 100
        if ret_6m < 15:
            return False
    return True


def detect_vcp(df, idx, lookback=60):
    if idx < lookback:
        return False, None
    window = df.iloc[idx-lookback:idx+1].copy()
    atr_recent = window["ATR20"].iloc[-5:].mean()
    atr_past = window["ATR20"].iloc[:10].mean()
    if pd.isna(atr_recent) or pd.isna(atr_past) or atr_past == 0:
        return False, None
    if atr_recent > atr_past * 0.85:
        return False, None
    pivot = window["High"].iloc[:-1].max()
    current_close = window["Close"].iloc[-1]
    if current_close < pivot * 0.93 or current_close > pivot * 1.10:
        return False, None
    ranges = []
    for i in range(0, lookback - 10, 10):
        high = window["High"].iloc[i:i+10].max()
        low = window["Low"].iloc[i:i+10].min()
        if high > 0:
            ranges.append((high - low) / high * 100)
    if len(ranges) < 3:
        return False, None
    last_range = ranges[-1]
    if last_range > 12:
        return False, None
    first_half_avg = sum(ranges[:len(ranges)//2]) / max(1, len(ranges)//2)
    if last_range >= first_half_avg * 0.85:
        return False, None
    return True, pivot


def check_bnf_lite_signal(df, idx):
    """BNF-LITE（乖離-15%、出来高1.0倍、BB-1.5σ）"""
    if idx < 25:
        return False
    close = df["Close"].iloc[idx]
    ma25 = df["MA25"].iloc[idx]
    vol = df["Volume"].iloc[idx]
    vol_avg = df["Vol20"].iloc[idx]
    bb_lower = df["BB_lower_1_5"].iloc[idx]
    if pd.isna(ma25) or pd.isna(vol_avg) or pd.isna(bb_lower):
        return False
    deviation = (close - ma25) / ma25 * 100
    if deviation > -15.0:
        return False
    if vol < vol_avg * 1.0:
        return False
    if close > bb_lower:
        return False
    return True


def check_momentum_signal(df, idx):
    """MOMENTUM: 20日高値ブレイク"""
    if idx < 200:
        return False, None
    close = df["Close"].iloc[idx]
    high = df["High"].iloc[idx]
    ma50 = df["MA50"].iloc[idx]
    ma200 = df["MA200"].iloc[idx]
    vol = df["Volume"].iloc[idx]
    vol_avg = df["Vol20"].iloc[idx]
    if pd.isna(ma50) or pd.isna(ma200) or pd.isna(vol_avg):
        return False, None
    if close < ma200 or close < ma50:
        return False, None
    prev_high = df["High"].iloc[max(0, idx-20):idx].max()
    if pd.isna(prev_high) or prev_high == 0:
        return False, None
    if high <= prev_high * 1.001:
        return False, None
    if vol < vol_avg * 1.5:
        return False, None
    ret_5d = (close / df["Close"].iloc[idx-5] - 1) * 100 if idx >= 5 else 0
    if ret_5d > 15:
        return False, None
    return True, prev_high


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  シグナルスキャン
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scan_signals(stocks, start_date, end_date, regime):
    """全銘柄をスキャンしてシグナルを検出"""
    signals = []

    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"),
                  BarColumn(), TaskProgressColumn(), console=console) as prog:
        task = prog.add_task("銘柄スキャン中...", total=len(stocks))

        for ticker, info in stocks.items():
            name, sector = info
            try:
                df = yf.download(ticker, start=start_date, end=end_date,
                                 progress=False, auto_adjust=True)
                if df.empty:
                    prog.advance(task)
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if len(df) < 200:
                    prog.advance(task)
                    continue

                df = prepare_indicators(df)
                last_idx = len(df) - 1
                last_close = df["Close"].iloc[last_idx]

                # 戦略ごとの検出（v2.1の環境別ロジック）

                # BNF-LITE: PANIC/BEARISH/NEUTRAL で発動
                if regime in ("PANIC", "BEARISH", "NEUTRAL"):
                    if check_bnf_lite_signal(df, last_idx):
                        signals.append({
                            "ticker": ticker.replace(".T", ""),
                            "name": name, "sector": sector,
                            "strategy": "BNF-LITE",
                            "entry_price": last_close,
                            "stop_price": last_close * 0.95,  # -5%
                            "target_price": df["MA25"].iloc[last_idx],  # 25日MA
                            "target_pct": (df["MA25"].iloc[last_idx] / last_close - 1) * 100,
                            "stop_pct": -5.0,
                            "regime": regime,
                            "priority": 1 if regime == "PANIC" else (2 if regime == "BEARISH" else 3),
                            "detail": f"乖離{(last_close/df['MA25'].iloc[last_idx]-1)*100:.1f}%"
                                      f", BB-1.5σ以下"
                                      f", 出来高{df['Volume'].iloc[last_idx]/df['Vol20'].iloc[last_idx]:.2f}倍",
                        })

                # MOMENTUM: BULLISH のみ
                if regime == "BULLISH":
                    mom_ok, pivot = check_momentum_signal(df, last_idx)
                    if mom_ok:
                        signals.append({
                            "ticker": ticker.replace(".T", ""),
                            "name": name, "sector": sector,
                            "strategy": "MOMENTUM",
                            "entry_price": pivot,
                            "stop_price": pivot * 0.95,  # -5%
                            "target_price": pivot * 1.10,  # +10%
                            "target_pct": 10.0,
                            "stop_pct": -5.0,
                            "regime": regime,
                            "priority": 1,
                            "detail": f"20日高値¥{pivot:,.0f}ブレイク"
                                      f", 出来高{df['Volume'].iloc[last_idx]/df['Vol20'].iloc[last_idx]:.2f}倍",
                        })

                # MINERVINI: BULLISH/NEUTRAL
                if regime in ("BULLISH", "NEUTRAL"):
                    if check_trend_template(df, last_idx):
                        vcp_ok, pivot = detect_vcp(df, last_idx)
                        if vcp_ok:
                            vol20 = df["Vol20"].iloc[last_idx]
                            current_high = df["High"].iloc[last_idx]
                            vol = df["Volume"].iloc[last_idx]
                            if not pd.isna(vol20) and vol >= vol20 * 1.4 and current_high >= pivot:
                                signals.append({
                                    "ticker": ticker.replace(".T", ""),
                                    "name": name, "sector": sector,
                                    "strategy": "MINERVINI",
                                    "entry_price": pivot,
                                    "stop_price": pivot * 0.93,  # -7%
                                    "target_price": pivot * 1.25,  # +25%で半分利確
                                    "target_pct": 25.0,
                                    "stop_pct": -7.0,
                                    "regime": regime,
                                    "priority": 1,
                                    "detail": f"Trend Template 8/8クリア"
                                              f", VCP検出, ピボット¥{pivot:,.0f}",
                                })

            except Exception:
                pass
            prog.advance(task)

    # 優先度順にソート
    signals.sort(key=lambda x: (x["priority"], -x.get("stop_pct", 0)))
    return signals


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  株数計算（1%リスク）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_position_size(signal, capital, risk_pct):
    """ポジションサイズ計算
    1トレードで資金の risk_pct% しかリスクを取らない
    """
    entry = signal["entry_price"]
    stop = signal["stop_price"]
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return 0, 0, 0

    risk_amount = capital * (risk_pct / 100)
    shares = int(risk_amount / risk_per_share)

    # 日本株は100株単位なので丸める（単元株）
    shares_adjusted = (shares // 100) * 100
    if shares_adjusted < 100:
        shares_adjusted = 100 if shares >= 50 else 0  # 最低100株、50株未満は見送り

    total_cost = shares_adjusted * entry
    actual_risk = shares_adjusted * risk_per_share

    return shares_adjusted, total_cost, actual_risk


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  表示関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def show_header():
    console.print()
    console.print("╔═══════════════════════════════════════════════════════════╗")
    console.print("║  [bold cyan]🎯 DAILY SCANNER v2.0[/] [dim]🛡 CB搭載版[/]                        ║")
    console.print("║  [dim]BNF + Minervini + MOMENTUM + サーキットブレーカー[/]      ║")
    console.print("╚═══════════════════════════════════════════════════════════╝")
    console.print()


def show_market_status(regime, signals_raw):
    """相場環境を表示"""
    regime_colors = {
        "BULLISH": "bold green",
        "NEUTRAL": "bold white",
        "BEARISH": "bold yellow",
        "PANIC":   "bold red",
    }
    regime_icons = {
        "BULLISH": "🚀", "NEUTRAL": "⚖️",
        "BEARISH": "⚠️", "PANIC": "🚨",
    }
    regime_desc = {
        "BULLISH": "強気相場。MOMENTUMとMINERVINIで順張り狙い",
        "NEUTRAL": "中立相場。両方受付、慎重に",
        "BEARISH": "弱気相場。BNF-LITEのみ、暴落株の反発狙い",
        "PANIC":   "パニック相場。BNF-LITE最優先、大きな利益チャンス",
    }

    t = Table(title="[bold]🌤 今日のマーケット環境[/]", box=box.DOUBLE_EDGE,
              show_header=False)
    t.add_column("", style="bold", width=20)
    t.add_column("", width=45)

    icon = regime_icons.get(regime, "")
    color = regime_colors.get(regime, "white")
    t.add_row("相場環境", f"{icon} [{color}]{regime}[/]")
    t.add_row("戦略方針", regime_desc[regime])

    # 具体的な数値
    if "n225_close" in signals_raw:
        n225 = signals_raw["n225_close"]
        ma200 = signals_raw.get("n225_ma200", 0)
        above = "✅ 上" if signals_raw.get("n225_above_200ma") else "❌ 下"
        t.add_row("日経225", f"¥{n225:,.0f}  (200MA: ¥{ma200:,.0f}) [{above}]")

    if "n225_1m_change" in signals_raw:
        change = signals_raw["n225_1m_change"]
        change_c = "green" if change > 0 else "red"
        t.add_row("日経1ヶ月変化", f"[{change_c}]{change:+.2f}%[/]")

    if "vix" in signals_raw:
        vix = signals_raw["vix"]
        vix_status = "平穏" if vix < 20 else ("警戒" if vix < 25 else ("高ストレス" if vix < 30 else "パニック"))
        vix_c = "green" if vix < 20 else ("yellow" if vix < 25 else "red")
        t.add_row("VIX恐怖指数", f"[{vix_c}]{vix:.2f} ({vix_status})[/]")

    if "sp500_close" in signals_raw:
        sp500 = signals_raw["sp500_close"]
        above_sp = "✅ 上" if signals_raw.get("sp500_above_200ma") else "❌ 下"
        t.add_row("S&P500", f"${sp500:,.2f}  [200MA {above_sp}]")

    console.print(t)
    console.print()


def show_circuit_breaker_status(is_halt, reason, details):
    """v2: サーキットブレーカー状態を目立つ形で表示"""
    if is_halt:
        panel_content = f"""[bold red]🔴 HALT（トレード停止）[/]

  [bold]発動理由:[/] {reason}

  [dim]─── 各指標の状態 ───[/]
  VIX:              {details.get('vix', 'N/A'):.2f} (閾値: {details['halt_vix_threshold']})
  日経1ヶ月変化:    {details.get('n225_1m_change', 0):+.1f}% (閾値: -{details['halt_n225_threshold']}%)
  直近連敗:         {details['consecutive_losses']}連敗 (閾値: {details['halt_losses_threshold']}連敗)

  [bold yellow]⚠ 本日は新規エントリーを見送ることを推奨します[/]
  [dim]既存保有ポジションは損切り/利確ルール通りに継続してください[/]"""

        console.print(Panel(
            panel_content,
            border_style="red",
            title="[bold red]🛡 サーキットブレーカー[/]",
            title_align="left"
        ))
    else:
        # NORMAL状態
        panel_content = f"""[bold green]🟢 NORMAL（通常運用）[/]

  [dim]─── 各指標の状態 ───[/]
  VIX:              {details.get('vix', 0):.2f} / {details['halt_vix_threshold']} [dim](安全域)[/]
  日経1ヶ月変化:    {details.get('n225_1m_change', 0):+.1f}% / -{details['halt_n225_threshold']}% [dim](安全域)[/]
  直近連敗:         {details['consecutive_losses']}連敗 / {details['halt_losses_threshold']}連敗 [dim](安全域)[/]

  [bold green]✓ 本日は通常通りエントリー可能です[/]"""

        console.print(Panel(
            panel_content,
            border_style="green",
            title="[bold green]🛡 サーキットブレーカー[/]",
            title_align="left"
        ))
    console.print()


def show_signals(signals, capital, risk_pct, max_positions, current_positions):
    """シグナル一覧を表示"""
    if not signals:
        console.print(Panel(
            "[yellow]今日はエントリーシグナルがありません。\n"
            "明日の朝に再度確認してください。[/]",
            border_style="yellow", title="[bold]⚠ シグナルなし[/]"
        ))
        return []

    available_slots = max_positions - current_positions

    # 表示するシグナル数を制限
    show_count = min(len(signals), available_slots) if available_slots > 0 else 0

    console.print(Rule(f"[bold cyan]🎯 本日のシグナル ({len(signals)}件検出、"
                       f"推奨エントリー: {show_count}件)[/]"))
    console.print()

    if available_slots <= 0:
        console.print(Panel(
            f"[yellow]既に{current_positions}銘柄を保有中です。\n"
            f"上限{max_positions}銘柄に到達しているため新規エントリーは見送り推奨。[/]",
            border_style="yellow"
        ))
        return []

    # 株数計算
    actionable_signals = []
    for s in signals[:show_count]:
        shares, cost, risk = calc_position_size(s, capital, risk_pct)
        if shares >= 100:
            s["shares"] = shares
            s["cost"] = cost
            s["actual_risk"] = risk
            actionable_signals.append(s)

    if not actionable_signals:
        console.print(Panel(
            "[yellow]シグナルは検出されましたが、最低100株に届くポジションがありません。\n"
            "資金サイズを増やすか、価格の安い銘柄を待ってください。[/]",
            border_style="yellow"
        ))
        return []

    # 戦略別カラー
    strategy_colors = {
        "BNF-LITE":  "magenta",
        "MOMENTUM":  "yellow",
        "MINERVINI": "cyan",
    }
    strategy_icons = {
        "BNF-LITE":  "📉",
        "MOMENTUM":  "🚀",
        "MINERVINI": "📈",
    }

    for i, s in enumerate(actionable_signals, 1):
        s_color = strategy_colors.get(s["strategy"], "white")
        s_icon = strategy_icons.get(s["strategy"], "")

        t = Table(title=f"[bold]【{i}】{s_icon} [{s_color}]{s['strategy']}[/] — "
                        f"[cyan]{s['name']}[/] ({s['ticker']})[/]",
                  box=box.ROUNDED, show_header=False)
        t.add_column("", style="bold", width=18)
        t.add_column("", width=48)

        t.add_row("業種", s["sector"])
        t.add_row("エントリー価格", f"[bold]¥{s['entry_price']:,.0f}[/]")
        t.add_row("損切り価格", f"[red]¥{s['stop_price']:,.0f} ({s['stop_pct']:+.1f}%)[/]")
        t.add_row("利確目標", f"[green]¥{s['target_price']:,.0f} ({s['target_pct']:+.1f}%)[/]")
        t.add_row("", "")
        t.add_row("推奨株数", f"[bold yellow]{s['shares']:,} 株[/]")
        t.add_row("必要資金", f"¥{s['cost']:,.0f}")
        t.add_row("想定リスク", f"[red]¥{s['actual_risk']:,.0f} (資金の{s['actual_risk']/capital*100:.2f}%)[/]")
        t.add_row("", "")
        t.add_row("シグナル詳細", f"[dim]{s['detail']}[/]")

        console.print(t)
        console.print()

    return actionable_signals


def show_sbi_order_format(signals):
    """SBI証券での発注用コピペフォーマット"""
    if not signals:
        return

    console.print(Rule("[bold magenta]📱 SBI証券 発注情報（コピペ用）[/]"))
    console.print()

    t = Table(box=box.DOUBLE_EDGE, title="[bold]SBI証券アプリ入力内容[/]")
    t.add_column("銘柄コード", style="bold cyan")
    t.add_column("銘柄名")
    t.add_column("数量", justify="right")
    t.add_column("指値(買)", justify="right", style="yellow")
    t.add_column("逆指値(損切)", justify="right", style="red")

    for s in signals:
        t.add_row(
            s["ticker"],
            s["name"][:12],
            f"{s['shares']:,}",
            f"¥{s['entry_price']:,.0f}",
            f"¥{s['stop_price']:,.0f}"
        )

    console.print(t)
    console.print()

    # 手順を表示
    instruction = """[bold yellow]📋 発注手順（SBI証券アプリ）[/]

  [bold]1.[/] SBI証券アプリを開く
  [bold]2.[/] 「取引」→「株式」→「現物買」
  [bold]3.[/] 銘柄コード入力 → 銘柄確認
  [bold]4.[/] 数量入力（上記の推奨株数）
  [bold]5.[/] 価格タイプ：[yellow]指値[/]
  [bold]6.[/] 価格入力（上記の指値）
  [bold]7.[/] 期間：[yellow]当日[/] または [yellow]今週中[/]
  [bold]8.[/] 確認して注文確定

  [bold red]⚠ エントリー後すぐに逆指値注文も仕込む：[/]
    「信用/現物」→「逆指値」で損切り価格を設定
    これで外出中も自動で損切りされます"""

    console.print(Panel(instruction, border_style="yellow"))
    console.print()


def show_summary(signals, capital, current_positions, max_positions):
    """サマリー"""
    total_cost = sum(s["cost"] for s in signals)
    total_risk = sum(s["actual_risk"] for s in signals)

    t = Table(title="[bold cyan]📊 本日のトレードサマリー[/]",
              box=box.DOUBLE_EDGE, show_header=False)
    t.add_column("", style="bold", width=22)
    t.add_column("", width=30, justify="right")
    t.add_row("運用資金", f"¥{capital:,.0f}")
    t.add_row("現在のポジション数", f"{current_positions} / {max_positions} 銘柄")
    t.add_row("本日の新規エントリー", f"{len(signals)} 銘柄")
    t.add_row("必要資金合計", f"¥{total_cost:,.0f}")
    t.add_row("想定最大損失", f"[red]¥{total_risk:,.0f} ({total_risk/capital*100:.2f}%)[/]")
    if total_cost > 0:
        t.add_row("資金使用率", f"{total_cost/capital*100:.1f}%")
    console.print(t)
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  通知機能
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_line_notify(message, token):
    """LINE Notify経由で通知"""
    try:
        import requests
        url = "https://notify-api.line.me/api/notify"
        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": message}
        r = requests.post(url, headers=headers, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        console.print(f"[yellow]LINE通知エラー: {e}[/]")
        return False


def send_discord_webhook(message, webhook_url):
    """Discord Webhookで通知"""
    try:
        import requests
        data = {"content": message}
        r = requests.post(webhook_url, json=data, timeout=10)
        return r.status_code in (200, 204)
    except Exception as e:
        console.print(f"[yellow]Discord通知エラー: {e}[/]")
        return False


def format_notification(regime, signals, capital):
    """通知用メッセージを生成"""
    today = datetime.datetime.now().strftime("%Y-%m-%d（%a）")

    regime_icons = {"BULLISH": "🚀", "NEUTRAL": "⚖️",
                    "BEARISH": "⚠️", "PANIC": "🚨"}
    icon = regime_icons.get(regime, "")

    msg = f"\n━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📅 {today}\n"
    msg += f"{icon} 相場環境: {regime}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    if not signals:
        msg += "本日シグナルなし\n明日の朝、再確認してください"
        return msg

    msg += f"🎯 本日のシグナル: {len(signals)}件\n\n"

    strategy_icons = {"BNF-LITE": "📉", "MOMENTUM": "🚀", "MINERVINI": "📈"}

    for i, s in enumerate(signals, 1):
        s_icon = strategy_icons.get(s["strategy"], "")
        msg += f"【{i}】{s_icon} {s['strategy']}\n"
        msg += f"  {s['name']} ({s['ticker']})\n"
        msg += f"  買: ¥{s['entry_price']:,.0f} × {s['shares']}株\n"
        msg += f"  損切: ¥{s['stop_price']:,.0f}\n"
        msg += f"  目標: ¥{s['target_price']:,.0f}\n\n"

    total_cost = sum(s["cost"] for s in signals)
    msg += f"━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"必要資金: ¥{total_cost:,.0f}"

    return msg


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CSV保存
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def save_signals_csv(signals):
    """シグナルをCSV保存（履歴管理用）"""
    if not signals:
        return

    import csv
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"signals_{today}.csv"

    try:
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "ticker", "name", "sector", "strategy", "regime",
                "entry_price", "stop_price", "target_price",
                "shares", "cost", "actual_risk",
                "stop_pct", "target_pct", "detail"
            ])
            writer.writeheader()
            for s in signals:
                writer.writerow({k: s.get(k, "") for k in writer.fieldnames})
        console.print(f"[green]✓ CSV保存: {filename}[/]")
    except Exception as e:
        console.print(f"[yellow]CSV保存エラー: {e}[/]")


def build_html_dashboard(regime, signals_raw, is_halt, halt_reason, cb_details,
                         signals, actionable, capital, max_positions, current_positions):
    """GitHub Pages用のHTMLダッシュボードを生成"""
    now = datetime.datetime.now()
    date_str = now.strftime("%Y年%m月%d日（%a）")

    # 相場環境のカラー・ラベル
    regime_colors = {
        "BULLISH": "#00FF88",
        "NEUTRAL": "#00D4FF",
        "BEARISH": "#FFB800",
        "PANIC":   "#FF3355",
    }
    regime_icons = {"BULLISH": "🚀", "NEUTRAL": "⚖️", "BEARISH": "⚠️", "PANIC": "🚨"}
    regime_desc = {
        "BULLISH": "強気相場。MOMENTUM・MINERVINI順張り",
        "NEUTRAL": "中立相場。両方受付、慎重に",
        "BEARISH": "弱気相場。BNF-LITEのみ",
        "PANIC":   "パニック相場。BNF-LITE最優先",
    }
    regime_c = regime_colors.get(regime, "#FFFFFF")
    regime_ic = regime_icons.get(regime, "")

    # 相場指標の詳細HTML
    market_details = ""
    if "n225_close" in signals_raw:
        n225 = signals_raw["n225_close"]
        ma200 = signals_raw.get("n225_ma200", 0)
        above = "上" if signals_raw.get("n225_above_200ma") else "下"
        market_details += f'<tr><td style="padding:5px 10px;color:#888">日経225</td><td style="padding:5px 10px;text-align:right;color:#fff;font-family:monospace">¥{n225:,.0f} ({above})</td></tr>'
    if "n225_1m_change" in signals_raw:
        change = signals_raw["n225_1m_change"]
        change_c = "#00FF88" if change > 0 else "#FF3355"
        market_details += f'<tr><td style="padding:5px 10px;color:#888">日経1ヶ月変化</td><td style="padding:5px 10px;text-align:right;color:{change_c};font-family:monospace">{change:+.2f}%</td></tr>'
    if "vix" in signals_raw:
        vix = signals_raw["vix"]
        vix_c = "#00FF88" if vix < 20 else ("#FFB800" if vix < 25 else "#FF3355")
        market_details += f'<tr><td style="padding:5px 10px;color:#888">VIX恐怖指数</td><td style="padding:5px 10px;text-align:right;color:{vix_c};font-family:monospace">{vix:.2f}</td></tr>'
    if "sp500_close" in signals_raw:
        sp500 = signals_raw["sp500_close"]
        market_details += f'<tr><td style="padding:5px 10px;color:#888">S&amp;P500</td><td style="padding:5px 10px;text-align:right;color:#fff;font-family:monospace">${sp500:,.2f}</td></tr>'

    # サーキットブレーカー表示
    if is_halt:
        cb_html = f'''
        <div style="background:#3d1b1b;border:2px solid #FF3355;border-radius:8px;padding:20px;margin:16px 0;">
          <div style="font-size:32px;text-align:center;margin-bottom:10px;">🔴</div>
          <div style="color:#FF3355;font-size:18px;font-weight:bold;text-align:center;margin-bottom:10px;">HALT（トレード停止）</div>
          <div style="color:#ccc;font-size:13px;text-align:center;margin-bottom:12px;">発動理由: {halt_reason}</div>
          <div style="background:rgba(0,0,0,0.3);padding:12px;border-radius:6px;color:#ccc;font-size:12px;line-height:1.7;">
            📌 <b>推奨アクション</b><br>
            ・新規エントリー停止<br>
            ・既存ポジションは損切り/利確ルール厳守<br>
            ・明日以降の再判定を待つ
          </div>
        </div>
        '''
    else:
        vix_val = cb_details.get('vix', 0)
        n225_change = cb_details.get('n225_1m_change', 0)
        losses = cb_details['consecutive_losses']
        cb_html = f'''
        <div style="background:#1a2e1a;border:1px solid #00FF88;border-radius:8px;padding:16px;margin:16px 0;">
          <div style="color:#00FF88;font-size:16px;font-weight:bold;text-align:center;margin-bottom:12px;">🟢 NORMAL（通常運用）</div>
          <table width="100%" style="border-collapse:collapse;font-size:11px;">
            <tr><td style="padding:3px 8px;color:#888">VIX</td><td style="padding:3px 8px;text-align:right;color:#fff;font-family:monospace">{vix_val:.2f} / {cb_details['halt_vix_threshold']} <span style="color:#00FF88">✓</span></td></tr>
            <tr><td style="padding:3px 8px;color:#888">日経1M</td><td style="padding:3px 8px;text-align:right;color:#fff;font-family:monospace">{n225_change:+.1f}% / -{cb_details['halt_n225_threshold']}% <span style="color:#00FF88">✓</span></td></tr>
            <tr><td style="padding:3px 8px;color:#888">直近連敗</td><td style="padding:3px 8px;text-align:right;color:#fff;font-family:monospace">{losses}連敗 / {cb_details['halt_losses_threshold']}連敗 <span style="color:#00FF88">✓</span></td></tr>
          </table>
        </div>
        '''

    # シグナル表示
    if is_halt:
        signals_html = '<div style="text-align:center;padding:30px;color:#888;font-size:13px;">HALT状態のためスキャンをスキップしました</div>'
    elif not actionable:
        signals_html = '''
        <div style="background:#1a1f2e;border:1px solid #2a3040;border-radius:8px;padding:24px;text-align:center;color:#888;">
          <div style="font-size:36px;margin-bottom:10px;opacity:0.5;">📊</div>
          <div style="font-size:14px;line-height:1.7;">
            本日は該当するシグナルがありません<br>
            相場を落ち着いて見守りましょう
          </div>
          <div style="margin-top:16px;font-style:italic;font-size:11px;">
            「待てる人が最終的に勝つ」— BNF
          </div>
        </div>
        '''
    else:
        signals_html = ""
        strategy_colors = {
            "MOMENTUM": "#00FF88",
            "MINERVINI": "#FFB800",
            "BNF-LITE": "#00D4FF",
        }
        for s in actionable[:10]:  # 最大10件
            strat_c = strategy_colors.get(s["strategy"], "#888")
            shares = s.get("shares", 0)
            cost = s.get("cost", 0)
            risk = s.get("actual_risk", 0)
            signals_html += f'''
            <div style="background:#1a1f2e;border-left:3px solid {strat_c};border-radius:8px;padding:14px;margin-bottom:10px;">
              <table width="100%" style="border-collapse:collapse;">
                <tr>
                  <td>
                    <div style="color:#888;font-size:11px;font-family:monospace;">{s["ticker"]}</div>
                    <div style="color:#fff;font-size:15px;font-weight:bold;margin:2px 0;">{s["name"]}</div>
                    <span style="color:#888;font-size:10px;border:1px solid #333;padding:2px 6px;border-radius:3px;">{s["sector"]}</span>
                  </td>
                  <td style="text-align:right;">
                    <span style="background:{strat_c};color:#000;font-weight:bold;font-size:10px;padding:3px 8px;border-radius:3px;">{s["strategy"]}</span>
                  </td>
                </tr>
              </table>
              <table width="100%" style="margin-top:10px;border-collapse:collapse;">
                <tr>
                  <td style="background:rgba(0,0,0,0.3);padding:6px;text-align:center;border-radius:4px;">
                    <div style="color:#666;font-size:9px;">エントリー</div>
                    <div style="color:#00D4FF;font-size:13px;font-weight:bold;font-family:monospace;">¥{s["entry_price"]:,.0f}</div>
                  </td>
                  <td style="padding:0 4px;"></td>
                  <td style="background:rgba(255,51,85,0.1);padding:6px;text-align:center;border-radius:4px;">
                    <div style="color:#666;font-size:9px;">損切り</div>
                    <div style="color:#FF3355;font-size:13px;font-weight:bold;font-family:monospace;">¥{s["stop_price"]:,.0f}</div>
                  </td>
                  <td style="padding:0 4px;"></td>
                  <td style="background:rgba(0,255,136,0.1);padding:6px;text-align:center;border-radius:4px;">
                    <div style="color:#666;font-size:9px;">利確</div>
                    <div style="color:#00FF88;font-size:13px;font-weight:bold;font-family:monospace;">¥{s["target_price"]:,.0f}</div>
                  </td>
                </tr>
              </table>
              <div style="background:rgba(0,212,255,0.1);padding:10px;margin-top:8px;border-radius:4px;">
                <div style="color:#888;font-size:10px;margin-bottom:4px;">💰 購入プラン（1%リスク）</div>
                <div style="color:#00D4FF;font-size:13px;font-weight:bold;font-family:monospace;">
                  {shares}株 × ¥{s["entry_price"]:,.0f} = ¥{cost:,.0f}
                </div>
                <div style="color:#888;font-size:10px;margin-top:4px;">最大損失: ¥{risk:,.0f}</div>
              </div>
              <div style="color:#888;font-size:10px;margin-top:6px;font-style:italic;">{s.get("detail", "")}</div>
            </div>
            '''

    html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Scanner v2 - {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#0A0E1A;font-family:'Hiragino Sans',sans-serif;color:#E2EBF6;">
<div style="max-width:600px;margin:0 auto;padding:20px;">

<!-- ヘッダー -->
<div style="background:#0D1422;border-bottom:1px solid #1F2D45;padding:16px;border-radius:8px 8px 0 0;">
  <table width="100%">
    <tr>
      <td>
        <span style="background:#00D4FF;color:#000;font-family:monospace;font-size:11px;font-weight:bold;padding:4px 10px;letter-spacing:2px;border-radius:3px;">DAILY SCANNER v2</span>
        <span style="color:#888;font-size:12px;margin-left:10px;">BNF+Minervini+MOMENTUM</span>
      </td>
      <td style="text-align:right;color:#888;font-size:11px;font-family:monospace;">{date_str}</td>
    </tr>
  </table>
</div>

<!-- マーケット環境 -->
<div style="background:#111827;padding:20px;border:1px solid #1F2D45;">
  <div style="color:#666;font-size:10px;text-transform:uppercase;letter-spacing:2px;margin-bottom:8px;">MARKET REGIME</div>
  <div style="font-size:22px;font-weight:bold;color:{regime_c};margin-bottom:4px;">{regime_ic} {regime}</div>
  <div style="color:#ccc;font-size:13px;margin-bottom:12px;">{regime_desc.get(regime, "")}</div>
  <table width="100%" style="border-collapse:collapse;font-size:11px;">
    {market_details}
  </table>
</div>

<!-- サーキットブレーカー -->
<div style="background:#111827;padding:20px;border:1px solid #1F2D45;border-top:none;">
  <div style="color:#666;font-size:10px;text-transform:uppercase;letter-spacing:2px;margin-bottom:4px;">🛡 CIRCUIT BREAKER</div>
  {cb_html}
</div>

<!-- シグナル -->
<div style="background:#111827;padding:20px;border:1px solid #1F2D45;border-top:none;border-radius:0 0 8px 8px;">
  <div style="color:#666;font-size:10px;text-transform:uppercase;letter-spacing:2px;margin-bottom:12px;">
    TODAY'S SIGNALS ({len(actionable) if not is_halt else 0}件)
  </div>
  {signals_html}
</div>

<!-- フッター -->
<div style="padding:16px;text-align:center;color:#666;font-size:10px;line-height:1.6;">
  運用資金: ¥{capital:,.0f} / 同時保有上限: {max_positions}銘柄 (保有中: {current_positions})<br>
  1トレードリスク: 1% / 1日最大3銘柄推奨<br>
  ⚠ バックテストの過去データです。将来の利益を保証しません。<br>
  Daily Scanner v2 - {now.strftime("%H:%M:%S")} 更新
</div>

</div></body></html>'''
    return html


def save_html_dashboard(html):
    """HTMLレポートを public/ フォルダに保存"""
    os.makedirs("public", exist_ok=True)
    os.makedirs("public/history", exist_ok=True)

    # 最新版
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    # 履歴
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    with open(f"public/history/{today}.html", "w", encoding="utf-8") as f:
        f.write(html)

    console.print(f"[green]✓ HTMLダッシュボード保存: public/index.html[/]")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  メイン処理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    args = parse_args()

    show_header()

    # 期間設定（過去1年分のデータを取得、直近のシグナル判定に十分）
    today = datetime.datetime.now()
    start_date = (today - datetime.timedelta(days=400)).strftime("%Y-%m-%d")
    end_date = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # STEP 1: マーケット環境判定
    console.print(Rule("[bold blue]STEP 1/4  マーケット環境データ取得[/]"))
    console.print()
    console.print("  [dim]日経225, S&P500, VIX を取得中...[/]")
    global_data = fetch_global_data(start_date, end_date)
    regime, signals_raw = detect_market_regime(global_data)
    show_market_status(regime, signals_raw)

    # STEP 2: サーキットブレーカーチェック（v2新機能）
    console.print(Rule("[bold blue]STEP 2/4  🛡 サーキットブレーカー判定[/]"))
    console.print()

    # 過去の連敗数を読み込み
    if args.no_loss_tracking:
        consecutive_losses = 0
        console.print("[dim]連敗追跡: 無効[/]\n")
    else:
        consecutive_losses = load_trade_history()
        if consecutive_losses > 0:
            console.print(f"[yellow]過去履歴: 直近 [bold]{consecutive_losses}連敗[/] 中[/]\n")
        else:
            console.print("[green]過去履歴: 連敗なし（好調）[/]\n")

    cb_config = {
        "halt_vix": args.halt_vix,
        "halt_n225_drop": args.halt_n225_drop,
        "halt_consecutive_losses": args.halt_consecutive_losses,
    }
    is_halt, halt_reason, cb_details = check_circuit_breaker(
        signals_raw, consecutive_losses, cb_config
    )
    show_circuit_breaker_status(is_halt, halt_reason, cb_details)

    # HALTの場合は基本的にスキャンをスキップ（--force-scanで強制実行可能）
    if is_halt and not args.force_scan:
        console.print(Panel(
            "[bold yellow]本日のシグナルスキャンは見送ります[/]\n\n"
            "[white]HALT状態のため新規エントリーは非推奨です。\n"
            "既存保有ポジションは継続し、明日以降の再判定を待ってください。[/]\n\n"
            "[dim]強制的にスキャンしたい場合: --force-scan オプション[/]",
            border_style="yellow",
            title="[bold]⏸ トレード停止中[/]"
        ))
        console.print()

        # HALT時もHTMLダッシュボード更新
        html = build_html_dashboard(
            regime, signals_raw, is_halt, halt_reason, cb_details,
            [], [], args.capital, args.max_positions, args.current_positions
        )
        save_html_dashboard(html)

        # HALT時も通知（もし設定されていれば）
        if args.notify:
            msg = f"\n━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"📅 {datetime.datetime.now().strftime('%Y-%m-%d（%a）')}\n"
            msg += f"🔴 サーキットブレーカー発動\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
            msg += f"発動理由: {halt_reason}\n\n"
            msg += f"本日はトレード見送り推奨\n"
            msg += f"既存ポジションは継続管理"
            if args.notify == "line":
                token = os.environ.get("LINE_NOTIFY_TOKEN")
                if token:
                    send_line_notify(msg, token)
            elif args.notify == "discord":
                webhook = os.environ.get("DISCORD_WEBHOOK_URL")
                if webhook:
                    send_discord_webhook(msg, webhook)

        console.print("[dim]⚠ 投資は自己責任でお願いします。[/]\n")
        return

    # STEP 3: 銘柄スキャン
    console.print(Rule("[bold blue]STEP 3/4  銘柄スキャン[/]"))
    console.print()
    if is_halt and args.force_scan:
        console.print("[yellow]⚠ HALT状態ですが --force-scan のためスキャンします（参考用）[/]\n")
    signals = scan_signals(JAPAN_STOCKS, start_date, end_date, regime)
    console.print()

    # STEP 4: シグナル表示
    console.print(Rule("[bold blue]STEP 4/4  本日のエントリー推奨[/]"))
    console.print()
    actionable = show_signals(
        signals, args.capital, args.risk,
        args.max_positions, args.current_positions
    )

    if actionable:
        show_sbi_order_format(actionable)
        show_summary(actionable, args.capital, args.current_positions, args.max_positions)

    # CSV保存
    if args.save_csv and actionable:
        save_signals_csv(actionable)

    # HTMLダッシュボードを生成・保存
    html = build_html_dashboard(
        regime, signals_raw, is_halt, halt_reason, cb_details,
        signals, actionable, args.capital, args.max_positions, args.current_positions
    )
    save_html_dashboard(html)

    # 通知
    if args.notify and actionable:
        msg = format_notification(regime, actionable, args.capital)
        if args.notify == "line":
            token = os.environ.get("LINE_NOTIFY_TOKEN")
            if not token:
                console.print("[yellow]⚠ LINE_NOTIFY_TOKEN環境変数が設定されていません[/]")
            elif send_line_notify(msg, token):
                console.print("[green]✓ LINE通知送信完了[/]")
        elif args.notify == "discord":
            webhook = os.environ.get("DISCORD_WEBHOOK_URL")
            if not webhook:
                console.print("[yellow]⚠ DISCORD_WEBHOOK_URL環境変数が設定されていません[/]")
            elif send_discord_webhook(msg, webhook):
                console.print("[green]✓ Discord通知送信完了[/]")

    console.print()
    console.print("[dim]⚠ このツールはシグナル検出の補助です。最終判断はご自身で。[/]")
    console.print("[dim]⚠ 投資は自己責任です。[/]\n")


if __name__ == "__main__":
    main()
