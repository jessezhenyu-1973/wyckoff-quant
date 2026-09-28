#!/usr/bin/env python3
"""diag_m2_seedmean.py — M2 组合层多seed均值: 消除槽位顺序伪影后的真实期望
对 全A/HS300/深主板/创业板 各跑 30 个稳定seed, 报 均值/标准差/中位数/胜率.
单票层面不依赖槽位, 不受影响.
"""
import time
import statistics as st
import pandas as pd
import sys
sys.path.insert(0, '.')
import wyckoff as W

t0 = time.time()
p = pd.read_csv('/tmp/full_panel_test', dtype={'thscode': str}, low_memory=False)
p['date'] = pd.to_datetime(p['date'])
p = p.sort_values(['thscode', 'date'])
per_stock = {c: g for c, g in p.groupby('thscode', sort=False)}

def to_df(g):
    d = g[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
    d.set_index('date', inplace=True)
    return d

bse = lambda c: c.startswith(('43', '83', '87', '88', '89', '92'))
fullA = [c for c in per_stock if not bse(c) and c.startswith(('0', '3', '6')) and len(per_stock[c]) >= 60]
sz_main = [c for c in fullA if c.startswith(('000', '001', '002', '003'))]
sh_main = [c for c in fullA if c.startswith(('600', '601', '603', '605'))]
cyb = [c for c in fullA if c.startswith(('300', '301', '302'))]
kcb = [c for c in per_stock if c.startswith(('688', '689')) and len(per_stock[c]) >= 60]
hs300 = sorted(set(W.get_hs300_codes(300)) & set(fullA))
print(f'池子: 全A {len(fullA)} | 深 {len(sz_main)} | 沪 {len(sh_main)} | 创 {len(cyb)} | HS300 {len(hs300)}')

m2, prices, calendar = {}, {}, set()
for i, c in enumerate(fullA):
    df = to_df(per_stock[c])
    m2[c] = W.minimal_law_segments(df, mode='laws', upstall_exit=True)
    prices[c] = dict(zip(df.index.strftime('%Y%m%d'), df['close']))
    calendar |= set(prices[c].keys())
    if (i + 1) % 1500 == 0:
        print(f'...{i+1}')
calendar = sorted(calendar)

SEEDS = list(range(30))
pools = {'全A': fullA, '深主板': sz_main, '沪主板': sh_main,
         '创业板': cyb, 'HS300': hs300}
print(f"\n{'池子':<8}{'均值%':>8}{'标准差':>8}{'中位%':>8}{'P10%':>8}{'P90%':>8}{'>0占比':>8}{'最好':>7}{'最差':>7}")
for label, codes in pools.items():
    sub = {c: m2[c] for c in codes}
    rets = [W.portfolio_simulate(sub, prices, calendar, 1e6, buy_order=s, cost_bps=10)['total_return']
            for s in SEEDS]
    srt = sorted(rets)
    p10 = srt[int(0.1 * len(srt))]
    p90 = srt[len(srt) - 1 - int(0.1 * len(srt))]
    pos = sum(1 for x in rets if x > 0) / len(rets) * 100
    print(f"{label:<8}{st.mean(rets):>8.1f}{st.pstdev(rets):>8.1f}{st.median(rets):>8.1f}"
          f"{p10:>8.1f}{p90:>8.1f}{pos:>7.0f}%{max(rets):>7.1f}{min(rets):>7.1f}")
print(f'\n[30seed 均值估计完, 耗时 {time.time()-t0:.0f}s]')
