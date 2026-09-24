#!/usr/bin/env python3
"""
factors.py — 从「极简双参数」文章提炼的可量化因子 (非冗余部分)
文章: 《量化交易员含泪醒悟！扔掉几百个复杂因子，全程只靠2个参数》(2026-09-21)

提炼原则: 只保留 可机械判定 + 不与现有 S1/S2/S3/R1 信号冗余 的因子。
冗余不取: 良性放量(≈S3 SOS)、良性缩量(≈S2 Test)。
真正新增:
  F1 MA20 regime 过滤   — 空头(MA20下行+价在下方)不交易; 用于剔除 Spring 最深破陷阱
  F2 爆量离场          — 急涨后 量>爆量阈值×均量 → 触发离场 (增强 R1, 从预警升级为离场)
  F3 MA20 硬止损       — 收盘跌破 MA20 且持续 → 离场 (备选/与ATR吊灯并存)

判定口径全部机械化, 无主观:
  MA20  = SMA(close,20)
  空头  = MA20[0] < MA20[-5] 且 close < MA20   (近5日MA20重心下移+价格压线下方)
  多头  = MA20[0] > MA20[-5] 且 close > MA20
  震荡  = 其余
  爆量  = volume > BURST_VOL × 均量20 (默认3.0), 且近burst_lookback日内涨幅>up_th
"""
import numpy as np
import pandas as pd


class FactorParams:
    MA_PERIOD = 20          # 趋势判定均线 (文章固定20日线)
    SLOPE_LOOKBACK = 5     # MA20 重心斜率回看天数
    BURST_VOL = 3.0        # 爆量阈值 (量 ≥ 3×均量20)
    BURST_LOOKBACK = 10    # 爆量前上涨窗口
    UP_THRESHOLD = 0.10    # 爆量前窗口内累计涨幅 > 10% 才认"急涨后爆量"


def ma20_regime(df, p=None):
    """返回 (regime_series, allow_trade_series)
    regime ∈ {'bull','bear','range'}, allow_trade: 空头=False (不交易), 其余=True
    """
    p = p or FactorParams()
    ma = df['close'].rolling(p.MA_PERIOD, min_periods=p.MA_PERIOD).mean()
    slope = ma - ma.shift(p.SLOPE_LOOKBACK)
    bull = (slope > 0) & (df['close'] > ma)
    bear = (slope < 0) & (df['close'] < ma)
    regime = pd.Series('range', index=df.index)
    regime[bull] = 'bull'
    regime[bear] = 'bear'
    allow = regime != 'bear'  # 空头不交易
    return regime, allow, ma


def burst_volume(df, p=None):
    """爆量离场标志: 急涨窗口后 量>阈值×均量20 (文章"过量爆量=止盈拐点")
    返回 bool Series。当日为爆量拐点 → 触发离场。"""
    p = p or FactorParams()
    vma = df['volume'].rolling(20, min_periods=10).mean()
    base = df['close'].shift(p.BURST_LOOKBACK)
    up = (df['close'] / base - 1) > p.UP_THRESHOLD      # 近10日急涨
    burst = (df['volume'] > vma * p.BURST_VOL) & up       # 急涨后爆量
    return burst.fillna(False)


def ma20_stop(df, p=None, hold_bars=2):
    """MA20 硬止损: 收盘跌破 MA20 连续 hold_bars 根 → 离场标志 (True=应离场)
    返回 bool Series, 仅标记"有效跌破"(避免单日假摔)。"""
    p = p or FactorParams()
    ma = df['close'].rolling(p.MA_PERIOD, min_periods=p.MA_PERIOD).mean()
    below = (df['close'] < ma).astype(int)
    below = below.shift(1).fillna(0)  # 用前值判断"连续"
    # 连续 hold_bars 根收盘在MA20下方
    run = below.groupby((below != below.shift()).cumsum()).cumsum()
    return (run >= hold_bars).fillna(False)


def wyckoff_with_factors(df, p=None, fp=None, use_r1_exit=True, depth=9.9,
                         regime_filter=False, burst_exit=False, stop_ma20=False,
                         trend_confirm=False, time_stop=0, atr_mult=2.5):
    """威科夫 S1/S2/S3 + 文章因子合并 → 持仓段 (135口径, YYYYMMDD)。
    新增开关:
      regime_filter : 空头MA20 regime 不入场 (F1, 已证伪—会杀光Spring信号)
      burst_exit    : 持仓中遇 爆量拐点 离场 (F2, 增强R1)
      stop_ma20     : 收盘连续跌破MA20 离场 (F3, 备选止损)
      trend_confirm : Spring信号后 要求 MA20 斜率转正 才入场 (F4, 趋势作确认而非否决)
                     —— 把威科夫"底部陷阱"与文章"趋势跟随"缝合: Spring找陷阱, MA20拐头确认恢复
    """
    import wyckoff as W  # 复用 signals 里的检测
    from .signals import detect_wyckoff, WyckoffParams
    p = p or WyckoffParams()
    p.SPRING_DEPTH = depth
    fp = fp or FactorParams()
    sig = detect_wyckoff(df, p=p)
    if sig.empty:
        return []
    c = df['close']
    trv = pd.concat([df['high'] - df['low'],
                     (df['high'] - c.shift()).abs(),
                     (df['low'] - c.shift()).abs()], axis=1).max(axis=1)
    atr = trv.rolling(14, min_periods=7).mean()

    regime, allow, ma = ma20_regime(df, fp)
    slope = ma - ma.shift(fp.SLOPE_LOOKBACK)
    burst = burst_volume(df, fp) if burst_exit else pd.Series(False, index=df.index)
    mstop = ma20_stop(df, fp) if ma20_stop else pd.Series(False, index=df.index)

    buys = sig[sig['sig'].isin(['S1', 'S2', 'S3'])].copy()
    r1 = sig[sig['sig'] == 'R1'].copy()
    r1_dates = set(r1['date']) if len(r1) else set()
    buy_map = {}
    for s in buys.itertuples():
        buy_map.setdefault(s.date, []).append(s)

    segs, cd, pos, pending = [], None, None, None
    idx = df.index
    close_arr, atr_arr = df['close'].to_numpy(), atr.to_numpy()
    ymd = lambda t: t.strftime('%Y%m%d')
    pending_fire_i = -10**9  # Spring 信号日 (F4 等待确认的起算点)
    pending_sig = None

    for i in range(60, len(df)):
        d = str(idx[i].date())
        if pos:
            highest = max(pos['highest'], close_arr[i])
            chand = highest - atr_mult * atr_arr[i] if not np.isnan(atr_arr[i]) else -1e18
            stop = max(pos['stop'], chand)
            exit_now = close_arr[i] < stop
            if use_r1_exit and d in r1_dates and idx[i] > pos['entry_ts']:
                exit_now = True
            if burst_exit and bool(burst.iloc[i]) and idx[i] > pos['entry_ts']:
                exit_now = True
            if stop_ma20 and bool(mstop.iloc[i]) and idx[i] > pos['entry_ts']:
                exit_now = True
            if time_stop and i - pos['entry_i'] >= time_stop:
                exit_now = True
            if exit_now:
                segs.append({'entry_date': pos['entry_date'], 'entry_price': pos['entry_px'],
                             'exit_date': ymd(idx[i]), 'exit_price': float(close_arr[i]),
                             'sig': pos['sig']})
                pos, cd, pending = None, idx[i], None
            continue
        if cd is not None and (idx[i] - cd).days <= 20:
            continue
        if regime_filter and not bool(allow.iloc[i]):
            continue  # 空头MA20 regime: 不入场 (F1)
        rows = buy_map.get(d, [])
        # ---- F4: Spring 触发后, 等 MA20 斜率转正才入场 (最多等 confirm 日) ----
        if trend_confirm:
            if pending is None and rows:
                pending = rows[0]
                pending_fire_i = i
            if pending is not None and (i - pending_fire_i) <= 20:
                if slope.iloc[i] > 0:  # MA20 拐头 → 确认恢复, 入场
                    s = pending
                    j = i + 1
                    if j < len(df) and not pd.isna(s.entry) and s.entry > 0:
                        pos = {'entry_i': j, 'entry_date': ymd(idx[j]),
                               'entry_px': float(s.entry), 'stop': float(s.stop),
                               'highest': float(s.entry), 'sig': s.sig, 'entry_ts': idx[j]}
                    pending = None
            if pending is not None and (i - pending_fire_i) > 20:
                pending = None  # 等太久, 放弃
            continue
        if not rows:
            continue
        s = rows[0]
        j = i + 1
        if j >= len(df) or pd.isna(s.entry) or s.entry <= 0:
            continue
        pos = {'entry_i': j, 'entry_date': ymd(idx[j]), 'entry_px': float(s.entry),
               'stop': float(s.stop), 'highest': float(s.entry), 'sig': s.sig,
               'entry_ts': idx[j]}
    if pos:
        i = len(df) - 1
        segs.append({'entry_date': pos['entry_date'], 'entry_price': pos['entry_px'],
                     'exit_date': ymd(idx[i]), 'exit_price': float(close_arr[i]),
                     'sig': pos['sig'] + '_eod'})
    return segs
