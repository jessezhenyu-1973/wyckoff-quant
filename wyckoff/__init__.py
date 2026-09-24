#!/usr/bin/env python3
"""
wyckoff — 威科夫交易法量化包 (独立仓库)
  data.py       数据获取 (hithink-finance CLI, 沪深300 + 个股日线前复权)
  signals.py    TR/Spring(S1)/Test(S2)/SOS(S3)/Upthrust(R1) 检测 + 持仓段提取
  portfolio.py  组合层模拟 (10%×5只) + 135 V18-ATR 对照组 + 单票复利
"""
from .data import get_hs300_codes, get_stock_history, df_to_csv
from .signals import (WyckoffParams, detect_wyckoff, wyckoff_segments,
                      s1_shallow_segments, bt_atr)
from .portfolio import (portfolio_simulate, v18_segments, single_equity)
from .factors import (FactorParams, ma20_regime, burst_volume, ma20_stop,
                      wyckoff_with_factors)
from .laws import (LawParams, bull_regime, wyckoff_volume_state,
                   minimal_law_segments)

__all__ = [
    'get_hs300_codes', 'get_stock_history', 'df_to_csv',
    'WyckoffParams', 'detect_wyckoff', 'wyckoff_segments', 's1_shallow_segments', 'bt_atr',
    'portfolio_simulate', 'v18_segments', 'single_equity',
    'FactorParams', 'ma20_regime', 'burst_volume', 'ma20_stop', 'wyckoff_with_factors',
    'LawParams', 'bull_regime', 'wyckoff_volume_state', 'minimal_law_segments',
]
