#!/usr/bin/env python3
"""校验面板数据: ①是否前复权 ②v18单票耗时 ③池子规模"""
import time, sys
import pandas as pd
sys.path.insert(0, '.')
import wyckoff as W

p = pd.read_csv('/tmp/full_panel_test', dtype={'thscode': str}, low_memory=False)
g = p[p.thscode == '601728.SH'].sort_values('date')
h = W.get_stock_history('601728.SH')  # 逐票拉取, 前复权
g2 = g.copy()
g2['date'] = pd.to_datetime(g2['date'])
m = g2.merge(h[['close']].reset_index(), left_on='date', right_on='date',
             suffixes=('_panel', '_hist'))
diff = ((m.close_panel - m.close_hist) / m.close_hist * 100).abs()
print(f'前复权比对 601728: 对齐 {len(m)} 天, 最大偏差 {diff.max():.2f}% 平均 {diff.mean():.3f}%')

t0 = time.time()
segs = W.v18_segments(h)
print(f'v18_segments 单票耗时 {time.time()-t0:.1f}s, 段数 {len(segs)}')

# 池子界定
codes = p.thscode.unique()
c0 = sum(c.startswith('000') or c.startswith('001') or c.startswith('002') or c.startswith('003') for c in codes)
c3 = sum(c.startswith('300') or c.startswith('301') for c in codes)
c6 = sum(c.startswith('600') or c.startswith('601') or c.startswith('603') or c.startswith('605') for c in codes)
c9 = sum(c.startswith(('43', '83', '87', '88', '89', '92')) for c in codes)
print(f'池子: 主板 {c0+c6} | 创业板 {c3} | 北交所 {c9} | 总 {len(codes)}')
# 数据完整度: 每票最少天数分布
daycount = p.groupby('thscode').size()
print(f'每票行数: min {daycount.min()} median {int(daycount.median())} max {daycount.max()}')
print(f'行数<120天(135需MA55+回看)的票: {(daycount<120).sum()}')
