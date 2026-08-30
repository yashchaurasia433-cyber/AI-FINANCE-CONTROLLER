"""Simple, auditable linear-trend forecast — deliberately not a black-box model; a finance-ops tool needs a forecast a reviewer can check by hand."""
from datetime import date, timedelta
from collections import defaultdict


def build_daily_settled_series(results):
    by_date = defaultdict(float)
    for r in results:
        if r['match_type'] not in ('exact', 'fuzzy'):
            continue
        by_date[r['bank_record']['value_date']] += r['bank_record']['amount']
    return [{'date': d, 'amount': round(v, 2)} for d, v in sorted(by_date.items())]


def linear_forecast(series, horizon_days=7):
    n = len(series)
    if n < 2:
        return {'history': series, 'forecast': []}

    xs = list(range(n))
    ys = [p['amount'] for p in series]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    slope = (num / den) if den != 0 else 0
    intercept = mean_y - slope * mean_x

    last_date = date.fromisoformat(series[-1]['date'])
    forecast = []
    for h in range(1, horizon_days + 1):
        x = n - 1 + h
        yhat = max(0.0, slope * x + intercept)
        forecast.append({'date': (last_date + timedelta(days=h)).isoformat(), 'amount': round(yhat, 2)})

    return {'history': series, 'forecast': forecast, 'slope': slope}
