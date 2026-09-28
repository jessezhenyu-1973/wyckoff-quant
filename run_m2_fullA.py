#!/usr/bin/env python3
"""
run_m2_fullA.py — M2 (极简双参数×威科夫定律量能+滞涨离场, 不用Spring) 分池拆解
目的: M2 全A组合层 +27.6% 跨池稳健, 拆到 沪主板/深主板/创业板/HS300 定位稳健性来源。
口径: 与 run_v18_fullA 完全同池同框架:
  池子: 全A(剔除科创/北交所) / 沪主板 / 深主板 / 创业板 / HS300交集
  单票占优: M2单票复利 vs 同票同池 V18单票 / B&H
  组合层: 10%×5 事件驱动 (M2 与 V18 各自同池组合模拟)
用法:
  python3 run_m2_fullA.py /tmp/fullA_panel
"""
import os
import csv
import time

import pandas as pd

import wyckoff as W


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('panel')
    ap.add_argument('--cash', type=float, default=1e6)
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
    cyb = [c for c in per_stock if c.startswith(('300', '301', '302')) and len(per_stock[c]) >= 60]
    kcb = [c for c in per_stock if c.startswith(('688', '689')) and len(per_stock[c]) >= 60]
    fullA = sz_main + sh_main + cyb
    hs300 = sorted(set(W.get_hs300_codes(300)) & set(fullA))
    print(f'池子: 全A {len(fullA)} | 沪主板 {len(sh_main)} | 深主板 {len(sz_main)} | '
          f'创业板 {len(cyb)} | HS300(交集) {len(hs300)}')

    kcb_all = sz_main + sh_main + cyb + kcb
    m2_map, v_map, eq_m2, eq_v, bh, prices, calendar = {}, {}, {}, {}, {}, {}, set()
    for i, c in enumerate(sorted(kcb_all)):
        df = to_df(per_stock[c])
        prices[c] = dict(zip(df.index.strftime('%Y%m%d'), df['close']))
        calendar |= set(prices[c].keys())
        m2_map[c] = W.minimal_law_segments(df, mode='laws', upstall_exit=True)
        v_map[c] = W.v18_segments(df)
        eq_m2[c] = W.single_equity(m2_map[c])
        eq_v[c] = W.single_equity(v_map[c])
        bh[c] = float(df['close'].iloc[-1] / df['close'].iloc[0])
        if (i + 1) % 500 == 0:
            print(f'  ...{i+1}/{len(kcb_all)}  [{time.time()-t0:.0f}s]')
    calendar = sorted(calendar)

    pools = {'全A(剔科创)': fullA, '沪主板': sh_main, '深主板': sz_main,
             '创业板': cyb, '科创板': kcb, 'HS300(对照)': hs300}
    SEEDS = [0, 1, 2, 3, 4]
    print(f"\n{'='*76}")
    print(f"M2 (定律量能+滞涨离场, 不用Spring) 分池拆解  vs  V18-ATR  期间 {calendar[0]}~{calendar[-1]}")
    print(f"组合层已修复顺序依赖: 主数字=字典序中性(buy_order='code'), 方差=5个seed稳定洗牌区间")
    hdr = (f"{'池子':<12}{'M2组合%':>9}{'M2回撤%':>9}{'V18组合%':>9}{'M2占优vsV18':>13}"
           f"{'M2占优vsB&H':>13}{'B&H均值%':>9}{'seed方差区间':>14}")
    print(hdr)
    rows = []
    for label, codes in pools.items():
        if not codes:
            continue
        sub_m2 = {c: m2_map[c] for c in codes}
        sub_v = {c: v_map[c] for c in codes}
        r_m2 = W.portfolio_simulate(sub_m2, prices, calendar, args.cash)
        r_v = W.portfolio_simulate(sub_v, prices, calendar, args.cash)
        seed_ret = [W.portfolio_simulate(sub_m2, prices, calendar, args.cash, buy_order=s)['total_return']
                    for s in SEEDS]
        n = len(codes)
        w_v = sum(1 for c in codes if eq_m2[c] > eq_v[c])
        w_bh = sum(1 for c in codes if eq_m2[c] > bh[c])
        bh_mean = sum(bh[c] for c in codes) / n * 100 - 100
        print(f"{label:<12}{r_m2['total_return']:>9}{r_m2['max_drawdown']:>9}"
              f"{r_v['total_return']:>9}{f'{w_v}/{n}={w_v/n*100:.0f}%':>13}"
              f"{f'{w_bh}/{n}={w_bh/n*100:.0f}%':>13}{bh_mean:>9.1f}"
              f"{f'[{min(seed_ret):.0f},{max(seed_ret):.0f}]':>14}")
        print(f"   {label}: M2 交易{r_m2['n_trades']}笔 胜率{r_m2['win_rate']}% | "
              f"V18 交易{r_v['n_trades']}笔 胜率{r_v['win_rate']}% | M2 seed明细 {[f'{x:.0f}' for x in seed_ret]}")
        rows.append([label, n, r_m2['total_return'], r_m2['max_drawdown'],
                     r_v['total_return'], f'{w_v}/{n}={round(w_v/n*100,1)}%',
                     f'{w_bh}/{n}={round(w_bh/n*100,1)}%', round(bh_mean, 1),
                     r_m2['n_trades'], r_m2['win_rate'],
                     f'[{min(seed_ret):.2f},{max(seed_ret):.2f}]', ';'.join(f'{x:.2f}' for x in seed_ret)])

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'm2_fullA_probe.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['pool', 'n_stocks', 'm2_return', 'm2_dd', 'v18_return',
                    'm2_winrate_vs_v18', 'm2_winrate_vs_bh', 'bh_mean',
                    'm2_n_trades', 'm2_win_rate', 'm2_seed_range', 'm2_seed_detail'])
        for row in rows:
            w.writerow(row)
    print(f'\n结果: {out}  [总耗时 {time.time()-t0:.0f}s]')


if __name__ == '__main__':
    main()
