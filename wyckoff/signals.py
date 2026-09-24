#!/usr/bin/env python3
"""
signals.py — 威科夫 TR/Spring/Test/SOS/Upthrust 检测 (量化工化, 自包含)
最小信号集:
  S1 Spring   — 底部TR内 跌破下界后当日收盘收回区间 + 下穿缩量 + 浅破(不深穿)
  S2 Test     — Spring 后10日内缩量再探底(不深破Spring低点) → 确认加仓点
  S3 SOS      — 放量收上TR上界 (给无Spring的 Schematic#2 情形)
  R1 Upthrust — 顶部TR 放量突破上界后当日收回 → 风控离场预警(仅A股做多场景用作离场)

TR(交易区间)判定:
  近 TR_LEN 日(≥MIN_TR_DAYS) 内 高低价差 ≤ TR_MAX_WIDTH
  且窗口内含 ≥1 根放量恐慌K线 (vol ≥ SC_VOL×20日均量) → SC/BC 密集区
  TR_low/TR_high = 窗口高低点

无未来函数: TR窗口截至 i-1 (当日才能跌破/突破前区); entry = 次日开盘。
数据获取见 data.py; 组合/对照见 portfolio.py。
"""
import numpy as np
import pandas as pd


class WyckoffParams:
    """参数 (第一版冻结值, 后续可网格)"""
    TR_LEN = 40          # 回看窗口(交易日): 识别当前处于TR
    TR_MAX_WIDTH = 0.25  # 区间最大幅宽 (high-low)/mid
    MIN_TR_DAYS = 20     # 区间最少持续天数 (因果: 横有多长竖有多高)
    SC_VOL = 1.8         # 高潮K线 量 ≥ 20日均量×SC_VOL
    SPRING_VOL = 1.0     # Spring 下穿日 量 ≤ 20日均量×SPRING_VOL (缩量洗盘)
    SPRING_DEPTH = 0.03  # Spring 浅破约束: 下穿低 ≥ tr_low×(1-DEPTH), 排除深破(Spring#1型)
    SPRING_RECLAIM = 0.0 # 收盘收回 TR_low 之上 多少(0=收回即可)
    TEST_DAYS = 10       # Spring 后 Test 观察窗口
    SOS_VOL = 1.5        # SOS 突破日 量 ≥ 20日均量×SOS_VOL
    ATR_PERIOD = 14
    ATR_MULT = 2.5       # chandelier 移动止损 (与 V18-ATR 一致)
    HARD_STOP = 0.99     # Spring 低点 × 0.99 为结构性硬止损
    COOLDOWN = 20        # 离场后冷却


def bt_atr(df, period):
    """真实波幅均值 (SMA口径, 与 135 ATR 一致)"""
    h, l, c = df['high'], df['low'], df['close']
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period // 2).mean()


def detect_wyckoff(df, p=None, cooldown_from=None):
    """对日线 DataFrame(open/high/low/close/volume, DatetimeIndex) 生成信号。
    返回 DataFrame: 每行 = 一个信号事件
      date, sig(S1/S2/S3/R1), tr_low, tr_high, entry, stop, vol_ratio, width
    entry = 信号日次日开盘。cooldown_from: 离场日期列表 — 离场后 p.COOLDOWN 日内不再发买入信号。
    """
    p = p or WyckoffParams()
    df = df.copy()
    df['vol_ma20'] = df['volume'].rolling(20, min_periods=10).mean()

    rows = []
    cd = pd.DatetimeIndex(cooldown_from or [])

    def _in_cd(d):
        if len(cd) == 0:
            return False
        j = cd.searchsorted(d)
        if j == 0:
            return False
        return (d - cd[j - 1]).days <= p.COOLDOWN

    for i in range(p.TR_LEN + 1, len(df)):
        w = df.index[i - p.TR_LEN: i]  # TR窗口截至 i-1 (不含当日) — 当日才能跌破/突破前区
        win = df.loc[w]
        tr_low, tr_high = win['low'].min(), win['high'].max()
        mid = (tr_low + tr_high) / 2
        width = (tr_high - tr_low) / mid if mid > 0 else 9.9
        # SC/BC 密集区: 窗口内存在恐慌放量K线
        sc_mask = (win['volume'] >= win['vol_ma20'] * p.SC_VOL) & (win.index > win.index[0])
        has_calm = sc_mask.any()
        is_tr = (width <= p.TR_MAX_WIDTH) and has_calm

        row = df.iloc[i]
        c, o, l, h, v = row['close'], row['open'], row['low'], row['high'], row['volume']
        vm = row['vol_ma20']
        date = str(df.index[i].date())

        if is_tr and vm > 0:
            # ---- S1 Spring: 下穿TR_low后收盘收回, 下穿缩量, 浅破(不深穿) ----
            depth_ok = l >= tr_low * (1 - p.SPRING_DEPTH)
            if (l < tr_low and c > tr_low * (1 + p.SPRING_RECLAIM)
                    and v <= vm * p.SPRING_VOL and depth_ok and not _in_cd(df.index[i])):
                stop = min(l * p.HARD_STOP, tr_low)
                rows.append(dict(date=date, sig='S1', tr_low=tr_low, tr_high=tr_high,
                                 entry=0.0, stop=stop, vol_ratio=v / vm,
                                 width=width, calm_ok=True))
            # ---- R1 Upthrust: 放量突破TR_high后当日收回 → 顶部风控预警 ----
            if h > tr_high and c < tr_high and v >= vm * p.SOS_VOL:
                rows.append(dict(date=date, sig='R1', tr_low=tr_low, tr_high=tr_high,
                                 entry=0.0, stop=0.0, vol_ratio=v / vm,
                                 width=width, calm_ok=True))

        # ---- S2 Test: Spring 后 TEST_DAYS 日内缩量再探底(不深破Spring低点) ----
        sp_recent = next((r for r in reversed(rows) if r['sig'] == 'S1'), None)
        if (sp_recent is not None and vm > 0
                and 0 < (df.index[i] - pd.Timestamp(sp_recent['date'])).days <= p.TEST_DAYS
                and l >= sp_recent['tr_low'] * 0.99 and l < sp_recent['tr_high']
                and v < vm and not _in_cd(df.index[i])):
            stop = min(l * p.HARD_STOP, sp_recent['stop'])
            rows.append(dict(date=date, sig='S2', tr_low=sp_recent['tr_low'], tr_high=sp_recent['tr_high'],
                             entry=0.0, stop=stop, vol_ratio=v / vm,
                             width=width, calm_ok=True))

        # ---- S3 SOS: 放量收上TR上界(无近期Spring时用) ----
        spring_recent = any(r['sig'] in ('S1', 'S2') for r in rows[-15:])
        if c > tr_high and v >= vm * p.SOS_VOL and not spring_recent:
            stop = max(tr_low, c * 0.97)
            rows.append(dict(date=date, sig='S3', tr_low=tr_low, tr_high=tr_high,
                             entry=0.0, stop=stop, vol_ratio=v / vm,
                             width=width, calm_ok=True))

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values('date').reset_index(drop=True)

    # 同一TR内 S1/S2/S3 只保留第一个买入信号(去重), R1 独立保留
    buy = out[out['sig'] != 'R1'].copy()
    keep, last_tr = [], None
    for _, r in buy.iterrows():
        key = round((r['tr_low'] + r['tr_high']) / 2, 3)
        if key == last_tr:
            continue
        keep.append(r)
        last_tr = key
    buy2 = pd.DataFrame(keep) if keep else out[out['sig'] == 'R1'].iloc[0:0]
    out = pd.concat([buy2, out[out['sig'] == 'R1']], ignore_index=True).sort_values('date')

    # entry = 信号日次日开盘
    out['entry'] = np.nan
    for k, d in enumerate(out['date']):
        idx = df.index.searchsorted(pd.Timestamp(d))
        out.iloc[k, out.columns.get_loc('entry')] = (
            df['open'].iloc[idx + 1] if idx + 1 < len(df) else np.nan)
    out = out.dropna(subset=['entry'])
    return out.reset_index(drop=True)


def wyckoff_segments(df, use_r1_exit=True, depth=9.9, time_stop=0, atr_mult=2.5):
    """威科夫信号 → 135 口径持仓段 (单票顺序持仓 + 20日冷却 + 吊灯止损 + 可选R1离场)。
    depth: 浅破约束(9.9=不限深, 即只用 Spring 不加浅破过滤)。
    返回: [{'entry_date','entry_price','exit_date','exit_price','sig'}]  日期口径 YYYYMMDD。
    """
    p = WyckoffParams()
    p.SPRING_DEPTH = depth
    sig = detect_wyckoff(df, p=p)
    if sig.empty:
        return []
    c = df['close']
    trv = pd.concat([df['high'] - df['low'],
                     (df['high'] - c.shift()).abs(),
                     (df['low'] - c.shift()).abs()], axis=1).max(axis=1)
    atr = trv.rolling(14, min_periods=7).mean()

    buys = sig[sig['sig'].isin(['S1', 'S2', 'S3'])].copy()
    r1 = sig[sig['sig'] == 'R1'].copy()
    r1_dates = set(r1['date']) if len(r1) else set()
    buy_map = {}
    for s in buys.itertuples():
        buy_map.setdefault(s.date, []).append(s)

    segs, cd, pos = [], None, None
    idx = df.index
    close_arr, atr_arr = df['close'].to_numpy(), atr.to_numpy()
    ymd = lambda ts: ts.strftime('%Y%m%d')

    for i in range(60, len(df)):
        d = str(idx[i].date())
        if pos:
            highest = max(pos['highest'], close_arr[i])
            chand = highest - atr_mult * atr_arr[i] if not np.isnan(atr_arr[i]) else -1e18
            stop = max(pos['stop'], chand)
            exit_now = close_arr[i] < stop
            if use_r1_exit and d in r1_dates and idx[i] > pos['entry_ts']:
                exit_now = True
            if time_stop and i - pos['entry_i'] >= time_stop:
                exit_now = True
            if exit_now:
                segs.append({'entry_date': pos['entry_date'], 'entry_price': pos['entry_px'],
                             'exit_date': ymd(idx[i]), 'exit_price': float(close_arr[i]),
                             'sig': pos['sig']})
                pos, cd = None, idx[i]
            continue
        if cd is not None and (idx[i] - cd).days <= 20:
            continue
        rows = buy_map.get(d, [])
        if not rows:
            continue
        s = rows[0]
        j = i + 1
        if j >= len(df) or pd.isna(s.entry) or s.entry <= 0:
            continue
        pos = {'entry_i': j, 'entry_date': ymd(idx[j]), 'entry_px': float(s.entry),
               'stop': float(s.stop), 'highest': float(s.entry), 'sig': s.sig,
               'entry_ts': idx[j]}
    if pos:  # 期末虚拟平仓
        i = len(df) - 1
        segs.append({'entry_date': pos['entry_date'], 'entry_price': pos['entry_px'],
                     'exit_date': ymd(idx[i]), 'exit_price': float(close_arr[i]),
                     'sig': pos['sig'] + '_eod'})
    return segs


def s1_shallow_segments(df, use_r1_exit=True, depth=0.03, time_stop=0, atr_mult=2.5):
    """S1-only (仅 Spring 信号) + 浅破约束 + 吊灯/R1离场 + 20日冷却 (步骤①探针)"""
    p = WyckoffParams()
    p.SPRING_DEPTH = depth
    sig = detect_wyckoff(df, p=p)
    if sig.empty:
        return []
    buys = sig[sig['sig'] == 'S1'].copy()
    r1 = sig[sig['sig'] == 'R1'].copy()
    r1_dates = set(r1['date']) if len(r1) else set()
    c = df['close']
    trv = pd.concat([df['high'] - df['low'],
                     (df['high'] - c.shift()).abs(),
                     (df['low'] - c.shift()).abs()], axis=1).max(axis=1)
    atr = trv.rolling(14, min_periods=7).mean()
    bm = {}
    for s in buys.itertuples():
        bm.setdefault(s.date, []).append(s)

    segs, cd, pos = [], None, None
    idx = df.index
    ca, aa = df['close'].to_numpy(), atr.to_numpy()
    ymd = lambda t: t.strftime('%Y%m%d')
    for i in range(60, len(df)):
        d = str(idx[i].date())
        if pos:
            hi = max(pos['highest'], ca[i])
            ch = hi - atr_mult * aa[i] if not np.isnan(aa[i]) else -1e18
            ex = ca[i] < max(pos['stop'], ch)
            if use_r1_exit and d in r1_dates and idx[i] > pos['entry_ts']:
                ex = True
            if time_stop and i - pos['entry_i'] >= time_stop:
                ex = True
            if ex:
                segs.append({'entry_date': pos['entry_date'], 'entry_price': pos['entry_px'],
                             'exit_date': ymd(idx[i]), 'exit_price': float(ca[i]), 'sig': pos['sig']})
                pos, cd = None, idx[i]
            continue
        if cd is not None and (idx[i] - cd).days <= 20:
            continue
        rows = bm.get(d, [])
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
                     'exit_date': ymd(idx[i]), 'exit_price': float(ca[i]),
                     'sig': pos['sig'] + '_eod'})
    return segs
