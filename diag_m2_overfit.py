#!/usr/bin/env python3
"""
diag_m2_overfit.py — M2 不过拟合验证: 阈值参数平台期检验
原则: 真实有效参数在邻域内应表现为平台(多数组合为正+稳定), 单点尖峰=过拟合.
M2 的可调阈值(其余全部冻结):
  DEMAND_TH : 第三定律净需求阈值 (上涨日量/下跌日量比), 默认 1.15
  SUPPLY_TH : 净供应阈值, 默认 0.85
  EFFORT_VOL: 第二定律努力阈值(量/VMA倍数), 默认 1.8
  RESULT_EPS: 结果阈值(当日涨幅), 默认 0.003
验证池: 266只HS300可得数据 (与 HS300 报告口径一致)
输出: 各参数扫 5 档, 组合层收益(中性序+单边10bp成本+30seed均值), 判定平台期宽度.
"""
import time
import statistics as stt
import pandas as pd
import sys

sys.path.insert(0, '.')
import wyckoff as W
from wyckoff.laws import LawParams

COST = 10
SEEDS = list(range(30))


class L2(LawParams):
    pass  # 可变阈值容器


def main():
    t0 = time.time()
    codes = W.get_hs300_codes(300)
    data = {}
    for c in codes:
        df = W.get_stock_history(c)
        if df is not None:
            data[c] = df
    print(f'HS300池 {len(data)} 只')
    prices = {c: dict(zip(d.index.strftime('%Y%m%d'), d['close'])) for c, d in data.items()}
    calendar = sorted(set(d for c in data for d in prices[c].keys()))

    def segs_for(code, lf, upstall_exit=True):
        return W.minimal_law_segments(data[code], mode='laws', upstall_exit=upstall_exit, lp=lf)

    def combo(segs_map):
        r_neu = W.portfolio_simulate(segs_map, prices, calendar, 1e6,
                                     buy_order='code', cost_bps=COST)['total_return']
        seed = [W.portfolio_simulate(segs_map, prices, calendar, 1e6,
                                     buy_order=s, cost_bps=COST)['total_return']
                for s in SEEDS]
        return r_neu, stt.mean(seed), stt.pstdev(seed), min(seed), max(seed)

    # 网格: 每个参数 5 档, 其余冻结在默认
    grid = {
        'DEMAND_TH': [1.05, 1.10, 1.15, 1.20, 1.30],
        'SUPPLY_TH': [0.75, 0.80, 0.85, 0.90, 1.00],
        'EFFORT_VOL': [1.5, 1.8, 2.0, 2.5, 3.0],
        'RESULT_EPS': [0.001, 0.003, 0.005, 0.008, 0.010],
    }
    print(f"\n{'参数':<10}{'取值':>7}  {'中性%':>8}{'seed均值%':>9}{'seedσ':>7}{'区间':>14}")
    print('-' * 60)
    for param, vals in grid.items():
        for v in vals:
            lf = L2()
            setattr(lf, param, v)
            segs = {c: segs_for(c, lf) for c in data}
            neu, mu, sd, lo, hi = combo(segs)
            flag = '  *默认' if (param, v) in [('DEMAND_TH', 1.15), ('SUPPLY_TH', 0.85),
                                                 ('EFFORT_VOL', 1.8), ('RESULT_EPS', 0.003)] else ''
            print(f"{param:<10}{v:>7}  {neu:>8.1f}{mu:>9.1f}{sd:>7.1f}"
                  f"{f'[{lo:.0f},{hi:.0f}]':>14}{flag}")
        print('-' * 60)
    print(f'[平台期检验完, 耗时 {time.time()-t0:.0f}s]')
    print('判定标准: 平台期 = 参数5档中≥3档 seed均值>0 且 各档相对默认值衰减<30%')


if __name__ == '__main__':
    main()
