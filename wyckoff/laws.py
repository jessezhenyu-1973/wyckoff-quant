#!/usr/bin/env python3
"""
laws.py — 威科夫三大定律的可量化实现 (日线极简形态), 用于替换「极简双参数」文章的粗量能
文章: 《量化交易员含泪醒悟！扔掉几百个复杂因子，全程只靠2个参数》

定位: 不用 S1/Spring 图式信号。纯「趋势方向 + 量能状态」双参数体系, 但把文章的
量能状态(单点 量/均量 三态判定)升级为威科夫三大定律的供需失衡+努力结果度量。

可量化表达 (全部机械化, 无前视):
  第三定律 供需:  近 SD_WINDOW 日 上涨日总量 / 下跌日总量 = demand_ratio
                  demand_ratio > DEMAND_TH → 净需求(+1), < SUPPLY_TH → 净供应(-1)
  第二定律 努力vs结果: 努力 effort = volume/VMA20; 结果 result = close.pct_change()
                  上方滞涨 upstall = effort > EFFORT_VOL 且 result < RESULT_EPS
                  (放量推不动 = 供应吸收努力, 趋势健康度差 → 过滤入场 / 触发离场)
  第一定律 因果:  服务于区间测算(累→果), 日线单根K线形态无映射, 本模块不启用

趋势方向 (文章参数1): close > MA20 且 MA20 重心(近5日)向上 → 多头 regime
组合层/止损口径与 run_wyckoff_* 完全一致 (单笔10%×5, ATR14吊灯2.5×, 锚定入场价不滚动)
"""
import numpy as np
import pandas as pd


class LawParams:
    MA_PERIOD = 20          # 文章固定 20 日线
    SLOPE_LOOKBACK = 5      # MA20 重心斜率回看
    VMA_PERIOD = 20         # 均量周期
    SD_WINDOW = 10          # 供需失衡滚动窗口
    DEMAND_TH = 1.15        # 上涨日/下跌日总量比 > 1.15 = 净需求
    SUPPLY_TH = 0.85        # < 0.85 = 净供应
    EFFORT_VOL = 1.8       # 努力阈值: 量 > 1.8×均量 才算"放量努力"
    RESULT_EPS = 0.003     # 结果阈值: 当日涨幅 < 0.3% 算"推不动"
    STALL_LOOKBACK = 3     # 努力结果过滤回看天数
    ARTICLE_VOL = 1.5      # 文章原版量能状态: 量 > 1.5×均量
    ATR_PERIOD = 14
    ATR_MULT = 2.5
    COOLDOWN = 20          # 离场后冷却天数


def bull_regime(df, p=None):
    """文章参数1: 多头 regime = close>MA20 且 MA20重心(近5日)向上. 返回 (bull, ma)"""
    p = p or LawParams()
    ma = df['close'].rolling(p.MA_PERIOD, min_periods=p.MA_PERIOD).mean()
    slope = ma - ma.shift(p.SLOPE_LOOKBACK)
    bull = ((df['close'] > ma) & (slope > 0)).fillna(False)
    return bull, ma


def wyckoff_volume_state(df, p=None):
    """第三定律(供需失衡) + 第二定律(努力vs结果) 的日线度量
    返回 DataFrame:
      demand_ratio : 近10日 上涨日总量/下跌日总量
      vol_state    : +1 净需求 / 0 中性 / -1 净供应
      upstall      : 当日上方滞涨 (放量推不动) bool
      upstall_any  : 近 STALL_LOOKBACK 日内出现过上方滞涨 (入场过滤用) bool
    """
    p = p or LawParams()
    close, vol = df['close'], df['volume']
    vma = vol.rolling(p.VMA_PERIOD, min_periods=10).mean()
    up = (close > close.shift(1)).astype(float)
    dn = (close < close.shift(1)).astype(float)
    upv = up * vol
    dnv = dn * vol
    dem = (upv.rolling(p.SD_WINDOW, min_periods=5).sum()
           / (dnv.rolling(p.SD_WINDOW, min_periods=5).sum() + 1e-9))
    state = pd.Series(0, index=df.index)
    state[dem > p.DEMAND_TH] = 1
    state[dem < p.SUPPLY_TH] = -1
    eff = vol / vma
    res = close.pct_change()
    upstall = ((eff > p.EFFORT_VOL) & (res < p.RESULT_EPS)).fillna(False)
    upstall_any = upstall.rolling(p.STALL_LOOKBACK, min_periods=1).max().fillna(0).astype(bool)
    return pd.DataFrame({'demand_ratio': dem, 'vol_state': state,
                         'upstall': upstall, 'upstall_any': upstall_any})


def minimal_law_segments(df, mode='laws', use_effort_filter=True, upstall_exit=False,
                         stop_ma20=False, atr_mult=2.5, cooldown=20):
    """极简双参数持仓段 (不用 S1 Spring). 口径与 wyckoff/portfolio.py 一致.

    入场 (i 日确认, i+1 日开盘进, 无前视):
      文章参数1 趋势: bull regime (close>MA20 且 MA20 重心向上)
      文章参数2 量能:
        mode='article' : 文章原版 量>1.5×VMA (单点放量)
        mode='laws'    : 威科夫第三定律 净需求 (vol_state==+1)
      use_effort_filter: 第二定律 — 近3日出现"上方滞涨"(放量推不动) 则不入场
    离场 (i 日收盘执行):
      ATR14×atr_mult 吊灯 (锚定入场价, 不滚动 — 对齐 V18 对照组口径)
      upstall_exit    : 持仓中遇 当日上方滞涨 → 离场 (第二定律)
      stop_ma20       : 收盘连续2根 < MA20 → 离场
      离场后 cooldown 日冷却
    返回 segs: [{entry_date, entry_price, exit_date, exit_price, sig}] (YYYYMMDD)
    """
    p = LawParams()
    bull, ma = bull_regime(df, p)
    vs = wyckoff_volume_state(df, p)
    close = df['close']
    trv = pd.concat([df['high'] - df['low'],
                     (df['high'] - close.shift()).abs(),
                     (df['low'] - close.shift()).abs()], axis=1).max(axis=1)
    atr = trv.rolling(p.ATR_PERIOD, min_periods=7).mean()
    vma = df['volume'].rolling(p.VMA_PERIOD, min_periods=10).mean()

    close_arr = close.to_numpy()
    open_arr = df['open'].to_numpy()
    bull_arr = bull.to_numpy()
    state_arr = vs['vol_state'].to_numpy()
    upstall_arr = vs['upstall'].to_numpy()
    stall_any_arr = vs['upstall_any'].to_numpy()
    atr_arr = atr.to_numpy()
    ma_arr = ma.to_numpy()
    art_arr = (df['volume'] > vma * p.ARTICLE_VOL).fillna(False).to_numpy()
    if stop_ma20:
        mstop = ma20_stop(df, p, hold_bars=2).to_numpy()

    idx = df.index
    segs, cd, pos = [], None, None
    ymd = lambda t: t.strftime('%Y%m%d')

    for i in range(60, len(df)):
        if pos:
            stop = pos['anchor'] - atr_mult * atr_arr[i] if not np.isnan(atr_arr[i]) else -1e18
            exit_now = close_arr[i] < stop
            if upstall_exit and bool(upstall_arr[i]) and i > pos['entry_i']:
                exit_now = True
            if stop_ma20 and bool(mstop[i]) and i > pos['entry_i']:
                exit_now = True
            if exit_now:
                segs.append({'entry_date': pos['entry_date'], 'entry_price': pos['entry_px'],
                             'exit_date': ymd(idx[i]), 'exit_price': float(close_arr[i]),
                             'sig': pos['sig']})
                pos, cd = None, idx[i]
            continue
        if cd is not None and (idx[i] - cd).days <= cooldown:
            continue
        if not bool(bull_arr[i]):
            continue
        if mode == 'article':
            vol_ok = bool(art_arr[i])
        else:
            vol_ok = int(state_arr[i]) == 1
        if not vol_ok:
            continue
        if use_effort_filter and bool(stall_any_arr[i]):
            continue
        j = i + 1
        if j >= len(df) or np.isnan(open_arr[j]) or open_arr[j] <= 0:
            continue
        segs_sig = 'M0a' if mode == 'article' else 'M1'
        pos = {'entry_i': j, 'entry_date': ymd(idx[j]), 'entry_px': float(open_arr[j]),
               'anchor': float(open_arr[j]), 'sig': segs_sig, 'entry_ts': idx[j]}
    if pos:  # 期末未平仓
        i = len(df) - 1
        segs.append({'entry_date': pos['entry_date'], 'entry_price': pos['entry_px'],
                     'exit_date': ymd(idx[i]), 'exit_price': float(close_arr[i]),
                     'sig': pos['sig'] + '_eod'})
    return segs


def ma20_stop(df, p=None, hold_bars=2):
    """收盘连续 hold_bars 根 < MA20 → True (应离场). 与 factors.ma20_stop 同逻辑."""
    p = p or LawParams()
    ma = df['close'].rolling(p.MA_PERIOD, min_periods=p.MA_PERIOD).mean()
    below = (df['close'] < ma).astype(int)
    below = below.shift(1).fillna(0)
    run = below.groupby((below != below.shift()).cumsum()).cumsum()
    return (run >= hold_bars).fillna(False)
