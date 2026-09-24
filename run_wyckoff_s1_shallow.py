#!/usr/bin/env python3
"""
run_wyckoff_s1_shallow.py — 步骤①: S1-only + 浅破收紧探针
Spring 按 ZeaFx 三型: 深破(Spring#1, 放量)最危险 → 加 下穿深度≤depth×tr_low 约束,
只保留缩量浅破型(Spring#2/#3)。全池266只, 对照 V18-ATR。
用法:
  python3 run_wyckoff_s1_shallow.py --depth 0.03
  python3 run_wyckoff_s1_shallow.py --depth 0.03 --no-r1
"""
import os
import argparse
import statistics as st

import wyckoff as W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--depth', type=float, default=0.03)
    ap.add_argument('--no-r1', action='store_true')
    ap.add_argument('--top', type=int, default=0)
    args = ap.parse_args()
    n = args.top if args.top > 0 else 300

    codes = W.get_hs300_codes(n)
    datasets = {}
    for c in codes:
        df = W.get_stock_history(c)
        if df is not None:
            datasets[c] = df
    print(f'可用数据 {len(datasets)} 只, 浅破深度={args.depth:.0%}')

    prices = {c: dict(zip(df.index.strftime('%Y%m%d'), df['close']))
              for c, df in datasets.items()}
    calendar = sorted(set(d for df in datasets.values() for d in df.index.strftime('%Y%m%d')))

    segs_w, segs_v, eq_w, eq_v = {}, {}, {}, {}
    for i, (code, df) in enumerate(sorted(datasets.items())):
        segs_w[code] = W.s1_shallow_segments(df, use_r1_exit=not args.no_r1, depth=args.depth)
        segs_v[code] = W.v18_segments(df)
        eq_w[code] = W.single_equity(segs_w[code])
        eq_v[code] = W.single_equity(segs_v[code])
        if (i + 1) % 50 == 0:
            print(f'  ...{i+1}/{len(datasets)}')

    res_w = W.portfolio_simulate(segs_w, prices, calendar, 1e6)
    res_v = W.portfolio_simulate(segs_v, prices, calendar, 1e6)
    n = len(eq_w)
    wins = sum(1 for c in eq_w if eq_w[c] > eq_v[c])
    r1_on = 'R1开' if not args.no_r1 else 'R1关'
    print(f"\n{'='*62}")
    print(f"威科夫 S1-only 浅破≤{args.depth:.0%} ({r1_on})  vs  V18-ATR  [{n}只]")
    print(f"{'指标':<14}{'威科夫S1浅破':>18}{'V18-ATR':>18}")
    for k, lab in [('total_return', '总收益%'), ('n_trades', '交易数'),
                   ('win_rate', '胜率%'), ('max_drawdown', '最大回撤%')]:
        print(f"{lab:<14}{res_w[k]:>18}{res_v[k]:>18}")
    print(f"单票占优率: {wins}/{n} = {wins/max(n,1)*100:.1f}%  (落地线≥60%)")


if __name__ == '__main__':
    main()
