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


def _utc(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    microsecond: int = 0,
) -> datetime.datetime:
    """Build an aware UTC datetime, abbreviated for the case tables below."""
    return datetime.datetime(
        year, month, day, hour, minute, second, microsecond, tzinfo=pytz.utc
    )


DAY_OF_MONTH_CASES = [
    ("day-before", "dia8", _utc(2025, 3, 7, 9, 0), _utc(2025, 3, 8, 9, 0)),
    ("same-day", "dia8", _utc(2025, 3, 8, 9, 0), _utc(2025, 4, 8, 9, 0)),
    ("same-day-midnight", "dia8", _utc(2025, 3, 8, 0, 0), _utc(2025, 4, 8, 0, 0)),
    ("same-day-late", "dia8", _utc(2025, 3, 8, 23, 59), _utc(2025, 4, 8, 23, 59)),
    (
        "same-day-with-microseconds",
        "dia8",
        _utc(2025, 3, 8, 9, 0, 30, 123456),
        _utc(2025, 4, 8, 9, 0, 30, 123456),
    ),
    ("day-after", "dia8", _utc(2025, 3, 9, 9, 0), _utc(2025, 4, 8, 9, 0)),
    ("year-rollover", "dia8", _utc(2025, 12, 8, 9, 0), _utc(2026, 1, 8, 9, 0)),
    ("first-of-month", "dia1", _utc(2025, 3, 1, 9, 0), _utc(2025, 4, 1, 9, 0)),
    # A day that does not exist in the target month clamps to that month's last
    # day (relativedelta semantics), so 31 January -> 28 February.
    (
        "last-day-of-short-month",
        "dia31",
        _utc(2025, 1, 31, 9, 0),
        _utc(2025, 2, 28, 9, 0),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("delta", "start", "expected"),
    [case[1:] for case in DAY_OF_MONTH_CASES],
    ids=[case[0] for case in DAY_OF_MONTH_CASES],
)
async def test_next_date_monthly_recurrence_rolls_forward(delta, start, expected):
    next_date = await NextDate().convert(None, delta, start=start)

    assert next_date == expected


@pytest.mark.asyncio
async def test_next_date_monthly_recurrence_advances_a_month_per_hop():
    """Rescheduling `dia8` from the 8th advances a month, never an hour.

    This is what the reminder loop does every time a monthly reminder fires.
    When the month fails to advance, the reminder re-fires every hour on the
    same day, which is the reported `rml dia8` defect.
    """
    date = _utc(2025, 3, 8, 9, 0)

    hops = []
    for _ in range(6):
        date = await NextDate().convert(None, "dia8", start=date)
        hops.append(date)

    assert hops == [
        _utc(2025, 4, 8, 9, 0),
        _utc(2025, 5, 8, 9, 0),
        _utc(2025, 6, 8, 9, 0),
        _utc(2025, 7, 8, 9, 0),
        _utc(2025, 8, 8, 9, 0),
        _utc(2025, 9, 8, 9, 0),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("delta", "day"),
    [("dia1", 1), ("dia8", 8), ("dia15", 15), ("dia28", 28)],
)
async def test_next_date_monthly_recurrence_hops_one_month_at_a_time(delta, day):
    """Two years of monthly hops must land on the expected NEXT month.

    For a recurrence on day N the next occurrence is day N of the next month
    when the start value already reached day N, and day N of the current month
    otherwise. Anything else is drift.
    """
    date = _utc(2025, 1, 1, 12, 30)

    for _ in range(24):
        next_date = await NextDate().convert(None, delta, start=date)
        month_index = date.year * 12 + date.month
        expected_month_index = month_index + (1 if date.day >= day else 0)

        assert next_date > date, f"{delta} from {date} did not move forward"
        assert next_date.day == day, f"{delta} from {date} lost the target day"
        assert next_date.year * 12 + next_date.month == expected_month_index, (
            f"{delta} from {date} landed on {next_date} instead of day {day} of "
            f"the expected month"
        )

        date = next_date
