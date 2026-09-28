#!/usr/bin/env python3
"""diag_m2.py — M2 分歧定位 (必须可复现才能下结论)
Q1: run_laws_fullA(5183池, 上一轮+27.57%) vs run_m2_star(5181池, 本轮+6.27%) 差在哪
Q2: m2_star 里 全A含科创 与 全A剔科创 结果完全相同(185笔/+6.27%), 但688单池有160笔 — 为什么混入后无变化
Q3: 两个池定义差的那几只票是谁, M2贡献多少
"""
import time
import pandas as pd
import sys
sys.path.insert(0, '.')
import wyckoff as W
from wyckoff.portfolio import portfolio_simulate

t0 = time.time()
p = pd.read_csv('/tmp/full_panel_test', dtype={'thscode': str}, low_memory=False)
p['date'] = pd.to_datetime(p['date'])
p = p.sort_values(['thscode', 'date'])
per_stock = {c: g for c, g in p.groupby('thscode', sort=False)}

def to_df(g):
    d = g[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
    d.set_index('date', inplace=True)
    return d

# --- 池定义 (复刻两个脚本) ---
bse = lambda c: c.startswith(('43', '83', '87', '88', '89', '92'))
pool_laws = [c for c in p.thscode.unique() if not bse(c) and c.startswith(('0', '3', '6'))]
pool_laws = [c for c in pool_laws if len(per_stock[c]) >= 60]          # 5183
pool_m2 = ([c for c in per_stock if c.startswith(('000','001','002','003')) and len(per_stock[c])>=60]
       + [c for c in per_stock if c.startswith(('600','601','603','605')) and len(per_stock[c])>=60]
       + [c for c in per_stock if c.startswith(('300','301')) and len(per_stock[c])>=60]
       + [c for c in per_stock if c.startswith('688') and len(per_stock[c])>=60])  # 5181
only_laws = sorted(set(pool_laws) - set(pool_m2))
only_m2 = sorted(set(pool_m2) - set(pool_laws))
print(f'pool_laws(上一轮脚本) {len(pool_laws)} | pool_m2(本轮脚本) {len(pool_m2)}')
print(f'  只在上一轮: {only_laws}')
print(f'  只在本轮: {only_m2}')

# --- M2 段提取 (全池一次) ---
m2, prices, calendar = {}, {}, set()
for i, c in enumerate(sorted(set(pool_laws + pool_m2))):
    df = to_df(per_stock[c])
    m2[c] = W.minimal_law_segments(df, mode='laws', upstall_exit=True)
    prices[c] = dict(zip(df.index.strftime('%Y%m%d'), df['close']))
    calendar |= set(prices[c].keys())
    if (i + 1) % 1500 == 0:
        print(f'...{i+1}')
calendar = sorted(calendar)

# --- 可追踪版组合模拟: 返回实际成交过的code集合 ---
def simulate_track(all_segments, prices_by_code, cal, cash0=1e6, max_pos=5):
    from collections import defaultdict
    cash = cash0
    holdings = {}
    realized = []
    traded = set()
    events = defaultdict(list)
    for code, segs in all_segments.items():
        for s in segs:
            events[s['entry_date']].append(('buy', code, s))
            if s.get('exit_date'):
                events[s['exit_date']].append(('sell', code, s))
    for d in cal:
        for typ, code, s in events.get(d, []):
            if typ == 'sell' and code in holdings:
                h = holdings.pop(code)
                cash += h['shares'] * s['exit_price']
                realized.append(h['shares'] * (s['exit_price'] - h['entry_price']))
        for typ, code, s in events.get(d, []):
            if typ != 'buy' or code in holdings or len(holdings) >= max_pos:
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
            traded.add(code)
    return realized, traded

# Q1: 上一轮口径复现
r1, tr1 = simulate_track({c: m2[c] for c in pool_laws}, prices, calendar)
base1 = portfolio_simulate({c: m2[c] for c in pool_laws}, prices, calendar, 1e6)
print(f'\nQ1 上一轮口径(5183): {base1["total_return"]}% {base1["n_trades"]}笔  [上一轮报告 +27.57% 194笔]')
r4, tr4 = simulate_track({c: m2[c] for c in [c for c in pool_m2 if not c.startswith('688')]}, prices, calendar)
base4 = portfolio_simulate({c: m2[c] for c in [c for c in pool_m2 if not c.startswith('688')]}, prices, calendar, 1e6)
print(f'Q2 本轮4574口径: {base4["total_return"]}% {base4["n_trades"]}笔 | 688成交数 {len(tr1 & set(c for c in pool_laws if c.startswith("688")))}')
# Q2b: 本轮含科创 688 是否成交
n688 = len(tr1 & set(c for c in pool_laws if c.startswith('688')))
n_only_laws = len([c for c in tr1 if c in only_laws])
print(f'  上一轮口径里实际成交: 688票 {n688}只 | 只在上一轮池的票 {n_only_laws}只 -> {sorted(tr1 & set(only_laws))}')

# Q3: 差的那几只票的M2段与单票净值
for c in only_laws:
    segs = m2[c]
    eq = W.single_equity(segs)
    print(f'\nQ3 {c}: M2段 {len(segs)}个, 单票净值 {eq:.3f} (+{(eq-1)*100:.1f}%)')
    for s in segs[:8]:
        print(f'   {s["entry_date"]}->{s.get("exit_date")} {s["entry_price"]:.2f}->{s["exit_price"]:.2f} sig={s.get("sig")}')

print(f'\n[总耗时 {time.time()-t0:.0f}s]')
