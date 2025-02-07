import os
import sys

import pytz

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
        date = datetime.datetime(2021, 1, 1, tzinfo=pytz.utc) + datetime.timedelta(
            days=i
        )

        for format in formats:
            dateConverted = await Date().convert(None, date.strftime(format))
            assert date == dateConverted


@pytest.mark.asyncio
async def test_delta_to_date_converter():
    tests = [
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6).replace(tzinfo=pytz.utc),
            datetime.datetime(2024, 10, 25, hour=17, minute=6).replace(tzinfo=pytz.utc),
            "1d",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6).replace(tzinfo=pytz.utc),
            datetime.datetime(2024, 10, 24, hour=17, minute=16).replace(
                tzinfo=pytz.utc
            ),
            "10m",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6).replace(tzinfo=pytz.utc),
            datetime.datetime(2024, 10, 24, hour=18, minute=6).replace(tzinfo=pytz.utc),
            "1h",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6).replace(tzinfo=pytz.utc),
            datetime.datetime(2024, 10, 24, hour=18, minute=16).replace(
                tzinfo=pytz.utc
            ),
            "1h10m",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6).replace(tzinfo=pytz.utc),
            datetime.datetime(2026, 1, 26, hour=19, minute=16).replace(tzinfo=pytz.utc),
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
            datetime.datetime(2024, 10, 24, hour=17, minute=6).replace(tzinfo=pytz.utc),
            datetime.datetime(2024, 10, 25, hour=17, minute=0).replace(tzinfo=pytz.utc),
            "minutos00horas17",
        ],
        [
            datetime.datetime(2024, 10, 24, hour=17, minute=6).replace(tzinfo=pytz.utc),
            datetime.datetime(2024, 10, 25, hour=17, minute=0).replace(tzinfo=pytz.utc),
            "horas17minutos00",
        ],
        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16).replace(
                tzinfo=pytz.utc
            ),
            datetime.datetime(2024, 12, 21, hour=12, minute=16).replace(
                tzinfo=pytz.utc
            ),
            "h12",
        ],
        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16).replace(
                tzinfo=pytz.utc
            ),
            datetime.datetime(2024, 12, 21, hour=12, minute=0).replace(tzinfo=pytz.utc),
            "h12m00",
        ],
        [
            datetime.datetime(2024, 12, 20, hour=13, minute=16).replace(
                tzinfo=pytz.utc
            ),
            datetime.datetime(2024, 12, 21, hour=13, minute=0).replace(tzinfo=pytz.utc),
            "h13m00",
        ],
        [
            datetime.datetime(2024, 12, 20, hour=13, minute=00).replace(
                tzinfo=pytz.utc
            ),
            datetime.datetime(2024, 12, 20, hour=13, minute=16).replace(
                tzinfo=pytz.utc
            ),
            "m16",
        ],
        [
            datetime.datetime(2024, 12, 26, hour=8, minute=0).replace(tzinfo=pytz.utc),
            datetime.datetime(2024, 12, 27, hour=8, minute=0).replace(tzinfo=pytz.utc),
            "h8m00",
        ],
        [
            datetime.datetime(2025, 1, 30, hour=16, minute=7).replace(tzinfo=pytz.utc),
            datetime.datetime(2025, 2, 5, hour=16, minute=7).replace(tzinfo=pytz.utc),
            "dia5",
        ],
    ]

    for test in tests:
        date, expected, delta = test
        nextDate = await NextDate().convert(None, delta, start=date)

        assert expected == nextDate
