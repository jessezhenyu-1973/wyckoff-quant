#!/usr/bin/env python3
"""
data.py — 自包含数据获取 (从 135-strategy 解耦)
依赖: hithink-finance CLI (同花顺日线, 前复权), pandas
用法:
    from wyckoff.data import get_hs300_codes, get_stock_history
"""
import subprocess
import json
import os
import datetime

import pandas as pd


def get_hs300_codes(top_n=300):
    """取沪深300成分股 thscode 列表 (过滤北交所, 保流动性)"""
    result = subprocess.run([
        'hithink-finance', 'index', 'constituents',
        '--thscode', '000300.SH', '--format', 'json'
    ], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    data = json.loads(result.stdout)
    items = data.get('data', {}).get('item', [])
    codes = [i.get('thscode', '') for i in items if i.get('thscode')]
    codes = [c for c in codes if c.startswith(('6', '0'))]
    return codes[:top_n] if top_n and top_n > 0 else codes


def get_stock_history(thscode, start_date='20230101', end_date='20260813'):
    """拉个股日线 (前复权), 返回 DatetimeIndex 的 OHLCV DataFrame 或 None"""
    start_ms = int(datetime.datetime.strptime(start_date, '%Y%m%d').timestamp() * 1000)
    end_ms = int(datetime.datetime.strptime(end_date, '%Y%m%d').timestamp() * 1000)
    cache = f'/tmp/_wyckoff_cache_{thscode.replace(".", "_")}.json'
    result = subprocess.run([
        'hithink-finance', 'market', 'history',
        '--thscode', thscode,
        '--start-ms', str(start_ms), '--end-ms', str(end_ms),
        '--adjust', 'forward', '--output', cache
    ], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        with open(cache) as f:
            data = json.load(f)
    except Exception:
        return None

    inner = data.get('data') if isinstance(data, dict) else data
    if isinstance(inner, dict):
        items = inner.get('item', [])
        if not items and 'path' in inner:
            try:
                with open(inner['path']) as f2:
                    inner2 = json.load(f2)
                inner = inner2.get('data', []) if isinstance(inner2, dict) else inner2
                items = inner if isinstance(inner, list) else inner.get('item', [])
            except Exception:
                items = []
    elif isinstance(inner, list):
        items = inner
    else:
        items = []

    if not items:
        return None
    df = pd.DataFrame(items)
    if 'date_ms' in df.columns:
        df['date'] = pd.to_datetime(df['date_ms'], unit='ms')
    elif 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    else:
        return None
    df.set_index('date', inplace=True)
    df.sort_index(inplace=True)
    col_map = {}
    for old, new in [('open_price', 'open'), ('high_price', 'high'),
                     ('low_price', 'low'), ('close_price', 'close')]:
        if old in df.columns:
            col_map[old] = new
    if col_map:
        df.rename(columns=col_map, inplace=True)
    if 'close' not in df.columns:
        return None
    df = df[(df['close'] > 0) & (df.get('volume', 0) >= 0)]
    return df if len(df) >= 60 else None


def df_to_csv(df, path):
    """DataFrame (OHLCV, DatetimeIndex) → backtrader 可吃的 CSV"""
    r = df.reset_index()
    r['date'] = r['date'].dt.strftime('%Y%m%d')
    cols = ['date', 'open', 'high', 'low', 'close', 'volume']
    r[cols].to_csv(path, index=False, float_format='%.4f')
