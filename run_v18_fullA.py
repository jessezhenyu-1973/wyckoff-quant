#!/usr/bin/env python3
"""
run_v18_fullA.py — 135 V18-ATR 全A影响确认 (V18 实现= wyckoff/portfolio.py 的 v18_segments,
与 135 JointStrategy('atr') 同口径: 3买入信号 + ATR14×2.5吊灯锚定入场价, 无信号卖出)

输出:
  1) 各池子(全A/沪主板/深主板/创业板/HS300) V18 组合层结果 (10%×5)
  2) 单票占优率: V18 单票复利 vs 同票同期间买入持有(B&H)
  3) 定位 V18 在大市值池 vs 全市场的分化幅度
用法:
  hithink-finance market panel --start 2023-01-01 --end 2026-08-13 --output /tmp/fullA_panel --file-format csv
  python3 run_v18_fullA.py /tmp/fullA_panel
"""
import os
import csv
import time
import argparse

import pandas as pd

import wyckoff as W


def main():
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

    # 池子界定 (剔除北交所; 数据>=60行; 码表含 302系创业板/689科创CDR)
    sh_main = [c for c in per_stock if c.startswith(('600', '601', '603', '605')) and len(per_stock[c]) >= 60]
    sz_main = [c for c in per_stock if c.startswith(('000', '001', '002', '003')) and len(per_stock[c]) >= 60]
    cyb = [c for c in per_stock if c.startswith(('300', '301', '302')) and len(per_stock[c]) >= 60]
    fullA = sz_main + sh_main + cyb
    hs300 = sorted(set(W.get_hs300_codes(300)) & set(fullA))
    print(f'池子: 全A {len(fullA)} | 沪主板 {len(sh_main)} | 深主板 {len(sz_main)} | '
          f'创业板 {len(cyb)} | HS300(交集) {len(hs300)}')

    # 全A 逐票: V18 段 + B&H 单票净值 + 价格日历 (一次算好, 池子只是过滤)
    segs_map, bh, prices, calendar = {}, {}, {}, set()
    for i, c in enumerate(sorted(fullA)):
        df = to_df(per_stock[c])
        prices[c] = dict(zip(df.index.strftime('%Y%m%d'), df['close']))
        calendar |= set(prices[c].keys())
        segs_map[c] = W.v18_segments(df)
        bh[c] = float(df['close'].iloc[-1] / df['close'].iloc[0])  # 全期间买入持有
        if (i + 1) % 500 == 0:
            print(f'  ...{i+1}/{len(fullA)}  [{time.time()-t0:.0f}s]')
    calendar = sorted(calendar)

    eq = {c: W.single_equity(s) for c, s in segs_map.items()}
    COST = 10  # 单边真实成本(bps): 佣金2.5+滑点5~6+印花税摊 ~10bp, 双边~20bp
    SEEDS = list(range(30))

    pools = {'全A(5183)': fullA, '沪主板': sh_main, '深主板': sz_main,
             '创业板': cyb, 'HS300(对照)': hs300}
    print(f"\n{'='*72}")
    print(f"135 V18-ATR 全A影响确认  (V18=3买入信号+ATR14×2.5吊灯, 组合10%×5)  期间 {calendar[0]}~{calendar[-1]}")
    print(f"口径: 中性序(code) | 真实成本 单边{COST}bp | 30-seed均值(消除槽位随机)")
    hdr = (f"{'池子':<12}{'V18中性%':>9}{'V18@0cost%':>11}{'30seed均值%':>11}{'seedσ':>6}"
           f"{'回撤%':>7}{'单票占优vsB&H':>14}{'B&H均值%':>9}")
    print(hdr)
    rows = []
    import statistics as stt
    for label, codes in pools.items():
        if not codes:
            continue
        sub = {c: segs_map[c] for c in codes}
        r_neu = W.portfolio_simulate(sub, prices, calendar, args.cash, buy_order='code',
                                     cost_bps=COST)
        r_zero = W.portfolio_simulate(sub, prices, calendar, args.cash, buy_order='code',
                                     cost_bps=0.0)
        seed_ret = [W.portfolio_simulate(sub, prices, calendar, args.cash, buy_order=s,
                                         cost_bps=COST)['total_return'] for s in SEEDS]
        n = len(codes)
        wins = sum(1 for c in codes if eq[c] > bh[c])
        bh_mean = sum(bh[c] for c in codes) / n * 100 - 100
        print(f"{label:<12}{r_neu['total_return']:>9}{r_zero['total_return']:>11}"
              f"{stt.mean(seed_ret):>11.1f}{stt.pstdev(seed_ret):>6.1f}"
              f"{r_neu['max_drawdown']:>7}{f'{wins}/{n}={wins/n*100:.0f}%':>14}{bh_mean:>9.1f}")
        rows.append([label, len(codes), r_neu['total_return'], r_zero['total_return'],
                     round(stt.mean(seed_ret), 2), round(stt.pstdev(seed_ret), 2),
                     r_neu['max_drawdown'], f'{wins}/{n}={round(wins/n*100,1)}%',
                     round(bh_mean, 1), r_neu['n_trades'], r_neu['win_rate']])
        print(f"   {label}: 交易{r_neu['n_trades']}笔 胜率{r_neu['win_rate']}%  "
              f"seed区间[{min(seed_ret):.0f},{max(seed_ret):.0f}]")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v18_fullA_probe.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['pool', 'n_stocks', 'v18_neutral_cost10', 'v18_zero_cost',
                    'seed_mean_cost10', 'seed_std', 'max_dd', 'winrate_vs_bh',
                    'bh_mean', 'n_trades', 'win_rate'])
        for row in rows:
            w.writerow(row)
    print(f'\n结果: {out}  [总耗时 {time.time()-t0:.0f}s]')


if __name__ == '__main__':
    main()
