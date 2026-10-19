"""Browser installation hints; never used as authentication credentials."""
from uuid import UUID
from ipaddress import ip_address


def browser_identity(request):
    if request is None:
        return None
    try:
        return str(UUID(request.headers.get("x-browser-id", "")))
    except (ValueError, AttributeError):
        return None


def request_ip(request):
    # Proxy trust is handled by the server, not arbitrary forwarded headers.
    try:
        return str(ip_address(request.client.host))
    except (ValueError, AttributeError):
        return None


def device_label(agent):
    ua = (agent or "").lower()
    if "iphone" in ua:
        device = "iPhone"
    elif "ipad" in ua:
        device = "iPad"
    elif "android" in ua:
        device = "Android phone" if "mobile" in ua else "Android tablet"
    elif "windows" in ua:
        device = "Windows PC"
    elif "macintosh" in ua or "mac os" in ua:
        device = "Mac"
    elif "linux" in ua:
        device = "Linux PC"
    else:
        device = "Unknown device"
    browser = next((name for markers, name in [
        (("edg/", "edga/", "edgios/"), "Edge"),
        (("opr/", "opera"), "Opera"),
        (("firefox/", "fxios/"), "Firefox"),
        (("chrome/", "crios/"), "Chrome"),
        (("safari/",), "Safari"),
    ] if any(marker in ua for marker in markers)), None)
    return f"{device} · {browser}" if browser else device
