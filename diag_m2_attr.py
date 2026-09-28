#!/usr/bin/env python3
"""diag_m2_attr.py — 干净归因: 27.57% vs 6.27% 是否仅由 689009/302132 两只票驱动
同一面板、同一 M2 信号, 仅切换池子(加/减这2只), 看组合层数字变化.
"""
import time
import pandas as pd
import sys
sys.path.insert(0, '.')
import wyckoff as W

t0 = time.time()
p = pd.read_csv('/tmp/full_pool_test' if False else '/tmp/full_panel_test', dtype={'thscode': str}, low_memory=False)
p['date'] = pd.to_datetime(p['date'])
p = p.sort_values(['thscode', 'date'])
per_stock = {c: g for c, g in p.groupby('thscode', sort=False)}

def to_df(g):
    d = g[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
    d.set_index('date', inplace=True)
    return d

# 宽前缀池 (run_laws_fullA 口径)
bse = lambda c: c.startswith(('43', '83', '87', '88', '89', '92'))
pool_wide = sorted(c for c in per_stock if not bse(c) and c.startswith(('0', '3', '6'))
                   and len(per_stock[c]) >= 60)

# 只需算一次 M2 段 + 价格 (全宽池)
m2, prices, calendar = {}, {}, set()
for i, c in enumerate(pool_wide):
    df = to_df(per_stock[c])
    m2[c] = W.minimal_law_segments(df, mode='laws', upstall_exit=True)
    prices[c] = dict(zip(df.index.strftime('%Y%m%d'), df['close']))
    calendar |= set(prices[c].keys())
    if (i + 1) % 1500 == 0:
        print(f'...{i+1}')
calendar = sorted(calendar)

A = set(pool_wide)                              # 5183
B = A - {'689009.SH'}                          # 去 689
C = A - {'302132.SZ'}                          # 去 302
D = A - {'689009.SH', '302132.SZ'}             # 去两只 = 5181 (m2 口径)

for label, pool in [('A 5183(宽池, 复现27.57)', A),
                    ('B 去689009', B),
                    ('C 去302132', C),
                    ('D 去两只=5181(m2口径,复现6.27)', D)]:
    r = W.portfolio_simulate({c: m2[c] for c in sorted(pool)}, prices, calendar, 1e6)
    print(f'{label:<26} M2组合 {r["total_return"]:>7}%  回撤 {r["max_drawdown"]:>6}%  交易 {r["n_trades"]:>3}笔')
print(f'\n[归因: A-D 若≈21点 = 两只票净贡献.  B/C 拆开看谁是主力]  耗时 {time.time()-t0:.0f}s')
