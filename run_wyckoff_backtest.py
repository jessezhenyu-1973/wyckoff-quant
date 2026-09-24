#!/usr/bin/env python3
"""
run_wyckoff_backtest.py — 主回测: 威科夫 S1/S2/S3 + ATR吊灯止损 vs 135 V18-ATR 对照
口径: 沪深300全池, 组合层(单笔10%资金×最多5只, 先到先得), 单票占优率≥60% 落地。
用法:
  python3 run_wyckoff_backtest.py --top 30    # 快速
  python3 run_wyckoff_backtest.py             # 全池
  python3 run_wyckoff_backtest.py --no-r1     # 关闭R1顶部离场
"""
import os
import csv
import argparse
import statistics as st

import wyckoff as W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=0)
    ap.add_argument('--no-r1', action='store_true', help='关闭R1顶部Upthrust离场')
    ap.add_argument('--cash', type=float, default=1e6)
    args = ap.parse_args()
    n = args.top if args.top > 0 else 300
    use_r1 = not args.no_r1

    print(f'获取沪深300(前{n})...')
    codes = W.get_hs300_codes(n)
    datasets = {}
    for c in codes:
        df = W.get_stock_history(c)
        if df is not None:
            datasets[c] = df
    print(f'可用数据 {len(datasets)} 只')

    prices = {c: dict(zip(df.index.strftime('%Y%m%d'), df['close']))
              for c, df in datasets.items()}
    calendar = sorted(set(d for df in datasets.values() for d in df.index.strftime('%Y%m%d')))

    print('提取威科夫持仓段 + V18-ATR对照组...')
    segs_w, segs_v, eq_w, eq_v = {}, {}, {}, {}
    for i, (code, df) in enumerate(sorted(datasets.items())):
        segs_w[code] = W.wyckoff_segments(df, use_r1_exit=use_r1)
        segs_v[code] = W.v18_segments(df)
        eq_w[code] = W.single_equity(segs_w[code])
        eq_v[code] = W.single_equity(segs_v[code])
        if (i + 1) % 30 == 0:
            print(f'  ...{i+1}/{len(datasets)}')

    res_w = W.portfolio_simulate(segs_w, prices, calendar, args.cash)
    res_v = W.portfolio_simulate(segs_v, prices, calendar, args.cash)
    ratio_w = res_w['total_return'] / res_w['max_drawdown'] if res_w['max_drawdown'] else 0
    ratio_v = res_v['total_return'] / res_v['max_drawdown'] if res_v['max_drawdown'] else 0

    n_st = len(eq_w)
    n_win = sum(1 for c in eq_w if eq_w[c] > eq_v[c])
    med_w = st.median(v - 1 for v in eq_w.values()) if eq_w else 0
    med_v = st.median(v - 1 for v in eq_v.values()) if eq_v else 0

    r1_on = 'R1离场=开' if use_r1 else 'R1离场=关'
    print(f"\n{'='*62}")
    print(f"威科夫 S1/S2/S3 + ATR吊灯止损 ({r1_on})  vs  135 V18-ATR  [{n_st}只, 组合10%×5]")
    print(f"{'指标':<14}{'威科夫':>16}{'V18-ATR(对照)':>20}")
    for k, lab in [('total_return', '总收益%'), ('n_trades', '交易数'),
                   ('win_rate', '胜率%'), ('max_drawdown', '最大回撤%')]:
        print(f"{lab:<14}{res_w[k]:>16}{res_v[k]:>20}")
    print(f"{'收益/回撤比':<13}{ratio_w:>16.2f}{ratio_v:>20.2f}")
    print(f"{'单票中位收益':<13}{med_w:>16.1%}{med_v:>20.1%}")
    print(f"单票占优率: {n_win}/{n_st} = {n_win/max(n_st,1)*100:.0f}%  (落地线≥60%)")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wyckoff_backtest_results.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['scheme', 'total_return', 'n_trades', 'win_rate', 'max_drawdown', 'ret_dd_ratio'])
        w.writerow([f'wyckoff_{r1_on}'] + [res_w[k] for k in
                    ('total_return', 'n_trades', 'win_rate', 'max_drawdown')] + [round(ratio_w, 2)])
        w.writerow(['v18_atr'] + [res_v[k] for k in
                    ('total_return', 'n_trades', 'win_rate', 'max_drawdown')] + [round(ratio_v, 2)])
        w.writerow(['single_stock_winrate', n_win, n_st, round(n_win / max(n_st, 1) * 100, 1), '', ''])
    print(f'\n结果: {out}')


if __name__ == '__main__':
    main()
