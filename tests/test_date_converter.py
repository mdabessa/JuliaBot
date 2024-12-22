import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import datetime
from itertools import product

from juliabot.converters import Date, DeltaToDate, NextDate



@pytest.mark.asyncio
async def test_date_converter():
    formats = [
        "%d/%m/%Y-%H:%M",
        "%H:%M-%d/%m/%Y",
        "%d/%m/%Y",
    ]

    for i in range(1, 365 * 2): # 2 years
        date = datetime.datetime(2021, 1, 1) + datetime.timedelta(days=i)

        for format in formats:
            dateConverted = await Date().convert(None, date.strftime(format))
            assert date == dateConverted


@pytest.mark.asyncio
async def test_delta_to_date_converter():
    ...

@pytest.mark.asyncio
async def test_next_date_converter():
    tests = [
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6),
            datetime.datetime(2024, 10, 25, hour=17, minute=0),
            "horas17minutos00"
        ],

        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16),
            datetime.datetime(2024, 12, 21, hour=12, minute=16),
            "h12"
        ],

        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16),
            datetime.datetime(2024, 12, 21, hour=12, minute=0),
            "h12m00"
        ],

        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16),
            datetime.datetime(2024, 12, 21, hour=13, minute=0),
            "h13m00"
        ],

        [
            datetime.datetime(2024, 12, 20, hour=13, minute=00),
            datetime.datetime(2024, 12, 20, hour=13, minute=16),
            "m16"
        ],
    ]

    for test in tests:
        date, expected, delta = test
        nextDate = await NextDate().convert(None, delta, start=date)
        
        assert expected == nextDate
