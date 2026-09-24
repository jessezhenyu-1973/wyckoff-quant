#!/usr/bin/env python3
"""
demo.py — 单票威科夫信号演示
用法:
  python3 demo.py 601728.SH           # 最近8个信号
  python3 demo.py 601728.SH --all     # 全部历史信号
"""
import argparse
import pandas as pd

import wyckoff as W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('code', nargs='?', default='601728.SH')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()

    df = W.get_stock_history(args.code)
    if df is None:
        raise SystemExit(f'{args.code} 取不到数据 (需 hithink-finance CLI)')
    sig = W.detect_wyckoff(df)
    print(f'{args.code} {df.index[0].date()} → {df.index[-1].date()}  共{len(df)}根K线, 信号{len(sig)}个')
    show = sig if args.all else sig.tail(8)
    if show.empty:
        print('无信号')
        return
    print(show.to_string())

    buys = sig[sig['sig'].isin(['S1', 'S2', 'S3'])]
    if not buys.empty:
        last = buys.iloc[-1]
        d = pd.Timestamp(last['date'])
        fut = df.loc[df.index > d]
        if len(fut) >= 10:
            r10 = fut['close'].iloc[min(9, len(fut) - 1)] / last['entry'] - 1
            r30 = fut['close'].iloc[min(29, len(fut) - 1)] / last['entry'] - 1
            mhh = fut['high'].max() / last['entry'] - 1
            mll = fut['low'].min() / last['entry'] - 1
            print(f"\n最近{last['sig']}@{last['date']}: entry={last['entry']:.2f} "
                  f"10日={r10:+.1%} 30日={r30:+.1%} 最大浮盈={mhh:+.1%} 最大回撤={mll:+.1%}")


if __name__ == '__main__':
    main()
