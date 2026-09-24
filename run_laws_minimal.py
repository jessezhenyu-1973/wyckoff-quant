#!/usr/bin/env python3
"""
run_laws_minimal.py — 极简双参数 × 威科夫三大定律 探针
思路: 不用 S1 Spring。文章参数1(趋势方向=MA20重心) 保留;
      文章参数2(量能状态) 升级为 威科夫第三定律供需失衡(净需求) + 第二定律努力vs结果(上方滞涨过滤)。
口径: 组合层 10%×5 / ATR14×2.5吊灯(锚定入场价, 不滚动), 与 V18-ATR 对照组完全一致。
用法:
  python3 run_laws_minimal.py --top 30
  python3 run_laws_minimal.py
"""
import os
import csv
import argparse

import wyckoff as W


def build_variants(df, args):
    a = W.minimal_law_segments(df, mode='article')
    b = W.minimal_law_segments(df, mode='laws')
    c = W.minimal_law_segments(df, mode='laws', upstall_exit=True)
    d = W.minimal_law_segments(df, mode='laws', upstall_exit=True, stop_ma20=True)
    return a, b, c, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=0)
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

    a_map, b_map, c_map, d_map, v_map = {}, {}, {}, {}, {}
    eq_v = {}
    for i, (code, df) in enumerate(sorted(datasets.items())):
        a, b, c, d = build_variants(df, args)
        a_map[code], b_map[code], c_map[code], d_map[code] = a, b, c, d
        v_map[code] = W.v18_segments(df)
        eq_v[code] = W.single_equity(v_map[code])
        if (i + 1) % 50 == 0:
            print(f'  ...{i+1}/{len(datasets)}')

    variants = {
        'M0 文章量能(1.5x均量)': a_map,
        'M1 定律量能(净需求)': b_map,
        'M2 M1+滞涨离场': c_map,
        'M3 M2+MA20止损': d_map,
        'V18-ATR对照': v_map,
    }
    results, eqs = {}, {}
    for label, m in variants.items():
        results[label] = W.portfolio_simulate(m, prices, calendar, args.cash)
        eqs[label] = {c: W.single_equity(s) for c, s in m.items()}

    n_st = len(eq_v)
    print(f"\n{'='*66}")
    print(f"极简双参数×威科夫定律量能  不用Spring  vs  V18-ATR  [{n_st}只, 组合10%×5]")
    hdr = f"{'口径':<20}{'总收益%':>9}{'回撤%':>8}{'收/回':>7}{'占优率(vs V18)':>16}"
    print(hdr)
    labels = ['M0 文章量能(1.5x均量)', 'M1 定律量能(净需求)',
              'M2 M1+滞涨离场', 'M3 M2+MA20止损', 'V18-ATR对照']
    for label in labels:
        r = results[label]
        if label == 'V18-ATR对照':
            win_col = '(对照基准)'
        else:
            wins = sum(1 for c in eqs[label] if eqs[label][c] > eq_v[c])
            win_col = f'{wins}/{n_st}={wins/max(n_st,1)*100:.0f}%'
        ratio = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] else 0
        print(f"{label:<20}{r['total_return']:>9}{r['max_drawdown']:>8}{ratio:>7.2f}"
              f"{win_col:>16}")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'laws_minimal_probe.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['variant', 'total_return', 'max_drawdown', 'ret_dd_ratio',
                    'winrate_vs_v18', 'n_trades', 'win_rate'])
        for label in labels:
            r = results[label]
            ratio = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] else 0
            if label == 'V18-ATR对照':
                wr = ''
            else:
                wins = sum(1 for c in eqs[label] if eqs[label][c] > eq_v[c])
                wr = round(wins / max(n_st, 1) * 100, 1)
            w.writerow([label, r['total_return'], r['max_drawdown'], round(ratio, 2),
                        wr, r['n_trades'], r['win_rate']])
    print(f'\n结果: {out}')


if __name__ == '__main__':
    main()
