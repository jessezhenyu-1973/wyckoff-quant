#!/usr/bin/env python3
"""
run_m2_star.py — M2 科创板定位: 688单池 / 688+创业板 / 含科创全A(5183, 复现+27.57%)
目的: 上一轮 M2 全A +27.57% 用的是含688的5183池, 本轮4574池(剔688)只有+6.27%。
      定位 M2 的稳健性来源到底是不是科创板。
"""
import os
import time

import pandas as pd

import wyckoff as W


def main():
    ap = __import__('argparse').ArgumentParser()
    ap.add_argument('panel')
    args = ap.parse_args()

    t0 = time.time()
    p = pd.read_csv(args.panel, dtype={'thscode': str}, low_memory=False)
    p['date'] = pd.to_datetime(p['date'])
    p = p.sort_values(['thscode', 'date'])
    per_stock = {c: g for c, g in p.groupby('thscode', sort=False)}

    def to_df(g):
        d = g[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        d.set_index('date', inplace=True)
        return d

    sh_main = [c for c in per_stock if c.startswith(('600', '601', '603', '605')) and len(per_stock[c]) >= 60]
    sz_main = [c for c in per_stock if c.startswith(('000', '001', '002', '003')) and len(per_stock[c]) >= 60]
    cyb = [c for c in per_stock if c.startswith(('300', '301')) and len(per_stock[c]) >= 60]
    kcb = [c for c in per_stock if c.startswith('688') and len(per_stock[c]) >= 60]
    fullA_no688 = sz_main + sh_main + cyb
    fullA_5183 = fullA_no688 + kcb

    print(f'池子: 科创688 {len(kcb)} | 688+创业板 {len(kcb)+len(cyb)} | '
          f'全A含科创 {len(fullA_5183)} | 全A剔科创 {len(fullA_no688)}')

    m2_map, prices, calendar = {}, {}, set()
    for i, c in enumerate(sorted(fullA_5183)):
        df = to_df(per_stock[c])
        prices[c] = dict(zip(df.index.strftime('%Y%m%d'), df['close']))
        calendar |= set(prices[c].keys())
        m2_map[c] = W.minimal_law_segments(df, mode='laws', upstall_exit=True)
        if (i + 1) % 1000 == 0:
            print(f'  ...{i+1}/{len(fullA_5183)}  [{time.time()-t0:.0f}s]')
    calendar = sorted(calendar)

    pools = {'科创688单池': kcb,
             '688+创业板': kcb + cyb,
             '全A含科创(5183,复现)': fullA_5183,
             '全A剔科创(4574)': fullA_no688}
    print(f"\n{'='*64}")
    for label, codes in pools.items():
        sub = {c: m2_map[c] for c in codes}
        r = W.portfolio_simulate(sub, prices, calendar, 1e6)
        print(f"{label:<18} M2组合 {r['total_return']:>8}%  回撤 {r['max_drawdown']:>6}%  "
              f"交易 {r['n_trades']:>4} 笔  胜率 {r['win_rate']}%")
    print(f'\n[总耗时 {time.time()-t0:.0f}s]')


if __name__ == '__main__':
    main()
