#!/usr/bin/env python3
"""
run_wyckoff_factors.py — 文章因子合并探针
测「极简双参数」文章中 MA20-regime / 爆量离场 / MA20止损 因子,
合入威科夫 Spring 后能否把 单票占优率(基准 S1-only 56%) 顶过 60% 落地线。
对照: 135 V18-ATR (与 run_wyckoff_backtest 同口径)。
用法:
  python3 run_wyckoff_factors.py --top 30
  python3 run_wyckoff_factors.py            # 全池
"""
import os
import csv
import argparse
import statistics as st

import wyckoff as W


def build_variants(df, args):
    """单票多口径持仓段 (F1否决式已证伪, 改测 F4确认 + F2/F3离场)"""
    base = W.s1_shallow_segments(df, use_r1_exit=not args.no_r1, depth=9.9)
    f4 = W.wyckoff_with_factors(df, trend_confirm=True, depth=9.9,
                                use_r1_exit=not args.no_r1)
    f2 = W.wyckoff_with_factors(df, burst_exit=True, depth=9.9,
                                use_r1_exit=not args.no_r1)
    f3 = W.wyckoff_with_factors(df, stop_ma20=True, depth=9.9,
                                use_r1_exit=not args.no_r1)
    f42 = W.wyckoff_with_factors(df, trend_confirm=True, burst_exit=True, depth=9.9,
                                  use_r1_exit=not args.no_r1)
    return base, f2, f3, f4, f42


def run(label, segs_map, prices, calendar, cash, eq_v=None, eq_base=None):
    res = W.portfolio_simulate(segs_map, prices, calendar, cash)
    eq = {c: W.single_equity(s) for c, s in segs_map.items()}
    return res, eq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=0)
    ap.add_argument('--no-r1', action='store_true')
    ap.add_argument('--cash', type=float, default=1e6)
    args = ap.parse_args()
    n = args.top if args.top > 0 else 300

    codes = W.get_hs300_codes(n)
    datasets = {}
    for c in codes:
        df = W.get_stock_history(c)
        if df is not None:
            datasets[c] = df
    print(f'获取沪深300(前{n})... 可用 {len(datasets)} 只')

    prices = {c: dict(zip(df.index.strftime('%Y%m%d'), df['close']))
              for c, df in datasets.items()}
    calendar = sorted(set(d for df in datasets.values() for d in df.index.strftime('%Y%m%d')))

    base_map, f2_map, f3_map, f4_map, f42_map, v_map = {}, {}, {}, {}, {}, {}
    eq_v = {}
    for i, (code, df) in enumerate(sorted(datasets.items())):
        base, f2, f3, f4, f42 = build_variants(df, args)
        base_map[code], f2_map[code], f3_map[code], f4_map[code], f42_map[code] = base, f2, f3, f4, f42
        v_map[code] = W.v18_segments(df)
        eq_v[code] = W.single_equity(v_map[code])
        if (i + 1) % 50 == 0:
            print(f'  ...{i+1}/{len(datasets)}')

    variants = {
        'S1-only(基准)': base_map,
        '+F4趋势确认': f4_map,
        '+F2爆量离场': f2_map,
        '+F3 MA20止损': f3_map,
        'F4+F2确认+爆量': f42_map,
        'V18-ATR对照': v_map,
    }
    results, eqs = {}, {}
    for label, m in variants.items():
        results[label] = W.portfolio_simulate(m, prices, calendar, args.cash)
        eqs[label] = {c: W.single_equity(s) for c, s in m.items()}

    n_st = len(eq_v)
    hdr = f"{'口径':<18}{'总收益%':>9}{'回撤%':>8}{'收/回':>7}{'占优率(vs V18)':>16}"
    print(f"\n{'='*62}")
    print(f"文章因子合并探针 (F1否决已证伪: Spring信号100%落在空头区)  vs  V18-ATR  [{n_st}只, 组合10%×5]")
    print(hdr)
    labels = ['S1-only(基准)', '+F4趋势确认', '+F2爆量离场', '+F3 MA20止损',
              'F4+F2确认+爆量', 'V18-ATR对照']
    for label in labels:
        r = results[label]
        if label == 'V18-ATR对照':
            win = ''
        else:
            wins = sum(1 for c in eqs[label] if eqs[label][c] > eq_v[c])
            win = f'{wins}/{n_st}={wins/max(n_st,1)*100:.0f}%'
        ratio = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] else 0
        win_col = win if win else '(对照基准)'
        print(f"{label:<18}{r['total_return']:>9}{r['max_drawdown']:>8}{ratio:>7.2f}"
              f"{win_col:>16}")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wyckoff_factor_probe.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['variant', 'total_return', 'max_drawdown', 'ret_dd_ratio',
                    'winrate_vs_v18'])
        for label in labels:
            r = results[label]
            ratio = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] else 0
            if label == 'V18-ATR对照':
                wr = ''
            else:
                wins = sum(1 for c in eqs[label] if eqs[label][c] > eq_v[c])
                wr = round(wins / max(n_st, 1) * 100, 1)
            w.writerow([label, r['total_return'], r['max_drawdown'], round(ratio, 2), wr])
    print(f'\n结果: {out}')


if __name__ == '__main__':
    main()
