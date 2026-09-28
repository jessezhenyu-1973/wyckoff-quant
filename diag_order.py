#!/usr/bin/env python3
"""diag_order.py — 证实/证伪: portfolio_simulate 结果是否依赖 信号dict插入顺序
同 5181 池 + 同 M2 段, 仅改变 dict 构建顺序 (sorted / 拼接 / 反序 / 随机),
看组合结果是否变化. 若变化 => 上轮 +27.57% 是顺序伪影, 需修组合层为顺序无关.
"""
import time
import random
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
pool = sorted(c for c in per_stock if not bse(c) and c.startswith(('0', '3', '6'))
              and len(per_stock[c]) >= 60)
pool_nostar = [c for c in pool if not c.startswith('688')]

m2, prices, calendar = {}, {}, set()
for c in pool:
    df = to_df(per_stock[c])
    m2[c] = W.minimal_law_segments(df, mode='laws', upstall_exit=True)
    prices[c] = dict(zip(df.index.strftime('%Y%m%d'), df['close']))
    calendar |= set(prices[c].keys())
calendar = sorted(calendar)
print(f'池 {len(pool)} (剔688={len(pool_nostar)}), M2段已建 [{time.time()-t0:.0f}s]')

def sim_in_order(order_codes):
    segs = {c: m2[c] for c in order_codes}
    return W.portfolio_simulate(segs, prices, calendar, 1e6)

variants = [
    ('A 4574 剔688, sorted顺序 (m2_fullA口径)', sim_in_order(sorted(pool_nostar))),
    ('B 4574 剔688, 反序', sim_in_order(sorted(pool_nostar, reverse=True))),
    ('C 5183 含688, sorted顺序', sim_in_order(sorted(pool))),
    ('D 5183 含688, 拼接顺序(sz+sh+cyb+kcb) (m2_star口径)',
     sim_in_order([c for c in pool_nostar if c.startswith(('000','001','002','003'))]
                  + [c for c in pool_nostar if c.startswith(('600','601','603','605'))]
                  + [c for c in pool_nostar if c.startswith(('300','301'))]
                  + [c for c in pool if c.startswith('688')])),
]
rng = random.Random(42)
for seed in (1, 2, 3):
    order = list(pool)
    random.Random(seed).shuffle(order)
    variants.append((f'E5183 随机顺序 seed={seed}', sim_in_order(order)))
order4574 = list(pool_nostar)
rng.shuffle(order4574)
variants.append((f'F4574 随机顺序 seed=42', sim_in_order(order4574)))

for label, r in variants:
    print(f'{label:<44} M2 {r["total_return"]:>8}% 回撤{r["max_drawdown"]:>7}% '
          f'交易{r["n_trades"]:>4} 胜率{r["win_rate"]}%')
print(f'\n[顺序依赖测试完, 耗时 {time.time()-t0:.0f}s]')
