import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import datetime

import pytest

from juliabot.converters import Date, DeltaToDate, NextDate


@pytest.mark.asyncio
async def test_date_converter():
    formats = [
        "%d/%m/%Y-%H:%M",
        "%H:%M-%d/%m/%Y",
        "%d/%m/%Y",
    ]

    for i in range(1, 365 * 2):  # 2 years
        date = datetime.datetime(2021, 1, 1) + datetime.timedelta(days=i)

        for format in formats:
            dateConverted = await Date().convert(None, date.strftime(format))
            assert date == dateConverted


@pytest.mark.asyncio
async def test_delta_to_date_converter():
    tests = [
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6),
            datetime.datetime(2024, 10, 25, hour=17, minute=6),
            "1d",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6),
            datetime.datetime(2024, 10, 24, hour=17, minute=16),
            "10m",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6),
            datetime.datetime(2024, 10, 24, hour=18, minute=6),
            "1h",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6),
            datetime.datetime(2024, 10, 24, hour=18, minute=16),
            "1h10m",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6),
            datetime.datetime(2026, 1, 26, hour=19, minute=16),
            "1y3mes2d2h10m",
        ],
    ]

    for test in tests:
        date, expected, delta = test
        dateConverted = await DeltaToDate().convert(None, delta, start=date)

        assert expected == dateConverted


@pytest.mark.asyncio
async def test_next_date_converter():
    tests = [
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6),
            datetime.datetime(2024, 10, 25, hour=17, minute=0),
            "minutos00horas17",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6),
            datetime.datetime(2024, 10, 25, hour=17, minute=0),
            "horas17minutos00",
        ],
        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16),
            datetime.datetime(2024, 12, 21, hour=12, minute=16),
            "h12",
        ],
        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16),
            datetime.datetime(2024, 12, 21, hour=12, minute=0),
            "h12m00",
        ],
        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16),
            datetime.datetime(2024, 12, 21, hour=13, minute=0),
            "h13m00",
        ],
        [
            datetime.datetime(2024, 12, 20, hour=13, minute=00),
            datetime.datetime(2024, 12, 20, hour=13, minute=16),
            "m16",
        ],
                [
            datetime.datetime(2024, 12, 26, hour=8, minute=0),
            datetime.datetime(2024, 12, 27, hour=8, minute=0),
            "h8m00",
        ],
    ]

    for test in tests:
        date, expected, delta = test
        nextDate = await NextDate().convert(None, delta, start=date)

        assert expected == nextDate
