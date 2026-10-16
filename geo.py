"""small geo math - distance, bearing, and walking a route at a given speed."""

import math

EARTH_R = 6371000.0  # meters


def haversine(a, b):
    # distance in meters between two (lat, lon) points
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def bearing(a, b):
    # compass bearing from a to b, degrees
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def route_length(points):
    return sum(haversine(points[i], points[i + 1]) for i in range(len(points) - 1))


def walk(points, speed_mps, interval_s):
    """
    yields (lat, lon, done_fraction) marching along the waypoints at speed_mps,
    one step every interval_s. good enough to fake a believable stroll/drive.
    linear lat/lon interp is fine at city scale.
    """
    if len(points) < 2:
        return
    step = speed_mps * interval_s  # meters per tick
    total = route_length(points)
    if total <= 0:
        return

    # precompute segment lengths so we can map "distance travelled" -> a point
    seg_len = [haversine(points[i], points[i + 1]) for i in range(len(points) - 1)]
    travelled = 0.0

    while travelled < total:
        # find which segment we're on
        d = travelled
        seg = 0
        while seg < len(seg_len) and d > seg_len[seg]:
            d -= seg_len[seg]
            seg += 1
        if seg >= len(seg_len):
            break
        t = d / seg_len[seg] if seg_len[seg] else 0
        lat, lon = lerp(points[seg], points[seg + 1], t)
        yield lat, lon, min(travelled / total, 1.0)
        travelled += step

    # always land exactly on the last point
    last = points[-1]
    yield last[0], last[1], 1.0
