#!/usr/bin/env python3
"""
run_laws_fullA.py — M1/M2 (极简双参数×威科夫定律量能) 全A市场回测
数据: hithink-finance market panel 本地全市场面板 (已校验=前复权, 4.6M行)
池子: 主板+创业板 (剔除北交所, 流动性), 且 数据>=60行
口径: 与 run_laws_minimal 完全一致 (M1净需求入场+滞涨过滤 / M2+滞涨离场),
      V18-ATR 对照组同口径 (ATR14×2.5吊灯锚定入场价, 组合10%×5)
用法:
  hithink-finance market panel --start 2023-01-01 --end 2026-08-13 --output /tmp/fullA_panel --file-format csv
  python3 run_laws_fullA.py /tmp/fullA_panel.csv
"""
import os
import csv
import time
import argparse

import pandas as pd

import wyckoff as W


def load_panel(path):
    p = pd.read_csv(path, dtype={'thscode': str}, low_memory=False)
    p['date'] = pd.to_datetime(p['date'])
    p = p.sort_values(['thscode', 'date'])
    return p


def pool_filter(codes, exclude_bse=True):
    out = []
    for c in codes:
        if c.startswith(('43', '83', '87', '88', '89', '92')):
            continue
        if c.startswith(('0', '3', '6')):
            out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('panel', help='全市场面板 csv (hithink-finance market panel 导出)')
    ap.add_argument('--cash', type=float, default=1e6)
    ap.add_argument('--limit', type=int, default=0, help='只取前N只(冒烟)')
    args = ap.parse_args()

    t0 = time.time()
    p = load_panel(args.panel)
    per_stock = {c: g.reset_index(drop=True) for c, g in p.groupby('thscode', sort=False)}
    codes = pool_filter(list(per_stock))
    if args.limit:
        codes = codes[:args.limit]
    # 数据>=60行 才入池 (v18 backtrader 与 M系列 都要求60+bar)
    codes = [c for c in codes if len(per_stock[c]) >= 60]
    print(f'全A池: {len(codes)} 只 (剔除北交所, 数据>=60行)  [加载 {time.time()-t0:.0f}s]')

    def to_df(g):
        d = g[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        d['date'] = pd.to_datetime(d['date'])
        d.set_index('date', inplace=True)
        return d

    prices, calendar = {}, set()
    m1_map, m2_map, v_map = {}, {}, {}
    for i, c in enumerate(codes):
        df = to_df(per_stock[c])
        prices[c] = dict(zip(df.index.strftime('%Y%m%d'), df['close']))
        calendar |= set(prices[c].keys())
        m1_map[c] = W.minimal_law_segments(df, mode='laws')
        m2_map[c] = W.minimal_law_segments(df, mode='laws', upstall_exit=True)
        v_map[c] = W.v18_segments(df)
        if (i + 1) % 500 == 0:
            print(f'  ...{i+1}/{len(codes)}  [{time.time()-t0:.0f}s]')
    calendar = sorted(calendar)

    variants = {
        'M1 定律量能(净需求)': m1_map,
        'M2 M1+滞涨离场': m2_map,
        'V18-ATR对照': v_map,
    }
    results, eqs, eq_v = {}, {}, {}
    for c, s in v_map.items():
        eq_v[c] = W.single_equity(s)
    for label, m in variants.items():
        results[label] = W.portfolio_simulate(m, prices, calendar, args.cash)
        eqs[label] = {c: W.single_equity(s) for c, s in m.items()}

    n_st = len(eq_v)
    print(f"\n{'='*66}")
    print(f"全A市场 M1/M2 × 威科夫定律量能 (不用Spring) vs V18-ATR  [{n_st}只, 组合10%×5]")
    print(f"{'口径':<22}{'总收益%':>9}{'回撤%':>8}{'收/回':>7}{'单票占优率(vs V18)':>20}")
    labels = ['M1 定律量能(净需求)', 'M2 M1+滞涨离场', 'V18-ATR对照']
    for label in labels:
        r = results[label]
        if label == 'V18-ATR对照':
            win_col = '(对照基准)'
        else:
            wins = sum(1 for c in eqs[label] if eqs[label][c] > eq_v[c])
            win_col = f'{wins}/{n_st}={wins/max(n_st,1)*100:.0f}%'
        ratio = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] else 0
        print(f"{label:<22}{r['total_return']:>9}{r['max_drawdown']:>8}{ratio:>7.2f}"
              f"{win_col:>20}")
    for label in ['M1 定律量能(净需求)', 'M2 M1+滞涨离场']:
        r = results[label]
        print(f"  {label}: 交易{r['n_trades']}笔, 胜率{r['win_rate']}%")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'laws_fullA_probe.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['variant', 'n_stocks', 'total_return', 'max_drawdown',
                    'ret_dd_ratio', 'winrate_vs_v18', 'n_trades', 'win_rate'])
        for label in labels:
            r = results[label]
            ratio = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] else 0
            if label == 'V18-ATR对照':
                wr = ''
            else:
                wins = sum(1 for c in eqs[label] if eqs[label][c] > eq_v[c])
                wr = round(wins / max(n_st, 1) * 100, 1)
            w.writerow([label, n_st, r['total_return'], r['max_drawdown'],
                        round(ratio, 2), wr, r['n_trades'], r['win_rate']])
    print(f'\n结果: {out}  [总耗时 {time.time()-t0:.0f}s]')


if __name__ == '__main__':
    main()
