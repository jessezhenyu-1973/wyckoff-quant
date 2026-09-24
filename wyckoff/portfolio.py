#!/usr/bin/env python3
"""
portfolio.py — 组合层模拟 + 135 V18-ATR 对照组 (自包含, 从 135-strategy 解耦)

- portfolio_simulate: 事件驱动组合模拟 (单笔10%资金, 最多同时5只, 先到先得)
- v18_segments: 135 V18-ATR 信号层的持仓段提取 (作为对照组基准)
  V18 = 3买入信号(红杏出墙/一阳穿三线/揭竿而起) + ATR14×2.5吊灯止损 (无信号卖出)
- single_equity: 单票顺序复利净值

用法:
    from wyckoff.portfolio import portfolio_simulate, v18_segments, single_equity
"""
import os
import tempfile
from collections import defaultdict

import pandas as pd
import backtrader as bt

from .data import df_to_csv


def single_equity(segs):
    """单票顺序复利净值 (不扣费, 与组合口径一致). 无段返回1.0"""
    eq = 1.0
    for s in segs:
        if s.get('entry_price') and s['entry_price'] > 0:
            eq *= 1.0 + (s['exit_price'] - s['entry_price']) / s['entry_price']
    return eq


def v18_segments(df, atr_mult=2.5):
    """提取 135 V18-ATR 持仓段 (entry/exit 日 + 价, 与 135 extract_segments 同口径)"""
    class V18(bt.Strategy):
        params = (('atr_mult', atr_mult), ('cool_down_bars', 10))

        def __init__(self):
            self.ma13 = bt.ind.SMA(self.data.close, period=13)
            self.ma34 = bt.ind.SMA(self.data.close, period=34)
            self.ma55 = bt.ind.SMA(self.data.close, period=55)
            self.vol_ma = bt.ind.SMA(self.data.volume, period=5)
            self.atr = bt.ind.ATR(self.data, period=14)
            self.highest = 0.0
            self.buy_bar = -1
            self.pending_entry = None
            self.segments = []

        def _is_downtrend(self):
            a = lambda i: (self.ma13[i], self.ma34[i], self.ma55[i])
            m0, m1, m2 = a(0), a(-1), a(-2)
            if not (m0[0] < m0[1] < m0[2]):
                return False
            return all(m0[j] < m1[j] < m2[j] for j in range(3))

        def _buy(self):
            c, o = self.data.close[0], self.data.open[0]
            m13, m34, m55 = self.ma13[0], self.ma34[0], self.ma55[0]
            m13p, m13p2 = self.ma13[-1], self.ma13[-2]
            v, vm = self.data.volume[0], self.vol_ma[0]
            if self._is_downtrend() or c < m55:
                return False
            m55_5 = self.ma55[-5]
            if m55_5 > 0 and (m55_5 - m55) / m55_5 > 0.05:
                return False
            if (m13p2 <= m13p and m13 > m13p and c > m13 and c > o and
                    v > vm and m13 > m34 > m55):
                return True
            if (c > o and o < m55 and o < m34 and o < m13 and c > m55 and c > m34 and c > m13
                    and v > vm * 2.0):
                return True
            if vm > 0:
                spread = (max(m13, m34, m55) - min(m13, m34, m55)) / max(m13, m34, m55)
                avg_s, cnt = 0.0, 0
                for i in range(5):
                    a13 = m13 if i == 0 else self.ma13[-i]
                    a34 = m34 if i == 0 else self.ma34[-i]
                    a55 = m55 if i == 0 else self.ma55[-i]
                    ms, mn = max(a13, a34, a55), min(a13, a34, a55)
                    avg_s += (ms - mn) / ms if ms > 0 else 0
                    cnt += 1
                if spread < 0.015 and avg_s / cnt < 0.02 and v > vm * 2.0 and c > o and c > m13:
                    return True
            return False

        def next(self):
            if len(self.data) < 60:
                return
            price = self.data.close[0]
            d = str(self.data.datetime.date(0)).replace('-', '')
            if self.position:
                if self.highest == 0:
                    self.highest = price
                # 严格对齐 135 JointStrategy('atr'): highest_price 入场设一次后不再滚动
                stop = self.highest - self.p.atr_mult * self.atr[0]
                if price < stop and self.pending_entry:
                    ed, ep = self.pending_entry
                    self.segments.append({'entry_date': ed, 'entry_price': ep,
                                           'exit_date': d, 'exit_price': price})
                    self.pending_entry = None
                    self.highest = 0
                    self.buy_bar = len(self.data) - 1
                return
            if self.buy_bar >= 0 and len(self.data) - 1 - self.buy_bar < self.p.cool_down_bars:
                return
            if self._buy():
                self.buy()
                self.pending_entry = (d, price)
                self.highest = price

        def notify_order(self, order):
            if order.status == order.Completed and order.isbuy() and self.pending_entry:
                d, _ = self.pending_entry
                self.pending_entry = (d, order.executed.price)

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    tmp.close()
    df_to_csv(df, tmp.name)
    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.GenericCSVData(
        dataname=tmp.name, dtformat='%Y%m%d',
        datetime=0, open=1, high=2, low=3, close=4, volume=5,
        openinterest=-1, headers=True))
    cerebro.addstrategy(V18)
    cerebro.broker.setcash(1000000)
    cerebro.broker.setcommission(commission=0.001)
    s = cerebro.run()[0]
    segs = s.segments
    if s.position and s.pending_entry:  # 期末未平仓
        ed, ep = s.pending_entry
        segs.append({'entry_date': ed, 'entry_price': ep,
                     'exit_date': str(df.index[-1]).replace('-', ''),
                     'exit_price': float(df['close'].iloc[-1])})
    os.unlink(tmp.name)
    return segs


def portfolio_simulate(all_segments, prices_by_code, calendar, cash0=1e6, max_pos=5):
    """事件驱动组合模拟: 持仓段即交易。entry日以10%资金买入(若名额与资金允许)。
    返回 dict: total_return / n_trades / win_rate / max_drawdown (%)
    """
    cash = cash0
    holdings = {}
    realized = []
    equity_curve = []
    events = defaultdict(list)
    for code, segs in all_segments.items():
        for s in segs:
            events[s['entry_date']].append(('buy', code, s))
            if s.get('exit_date'):
                events[s['exit_date']].append(('sell', code, s))
    for d in calendar:
        for typ, code, s in events.get(d, []):  # 先卖后买
            if typ == 'sell' and code in holdings:
                h = holdings.pop(code)
                pnl = h['shares'] * (s['exit_price'] - h['entry_price'])
                cash += h['shares'] * s['exit_price']
                realized.append(pnl)
        for typ, code, s in events.get(d, []):
            if typ != 'buy' or code in holdings:
                continue
            if len(holdings) >= max_pos:
                continue
            price = prices_by_code[code].get(d)
            if not price:
                continue
            alloc = cash * 0.10
            if alloc < price * 10:
                continue
            shares = int(alloc / price)
            cash -= shares * price
            holdings[code] = {'entry_price': price, 'shares': shares}
        eq = cash + sum(h['shares'] * prices_by_code[c].get(d, h['entry_price'])
                        for c, h in holdings.items())
        equity_curve.append((d, eq))
    final = equity_curve[-1][1] if equity_curve else cash0
    peak, maxdd = -1e18, 0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / peak)
    n_tr = len(realized)
    wins = sum(1 for p in realized if p > 0)
    return {
        'total_return': round((final - cash0) / cash0 * 100, 2),
        'n_trades': n_tr,
        'win_rate': round(wins / n_tr * 100, 1) if n_tr else 0,
        'max_drawdown': round(maxdd * 100, 2),
    }
