import aiohttp
import requests
from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token as get_csrf_token
from django.template.loader import render_to_string

from .app_settings import NEXTJS_SERVER_URL


def _get_context(html: str, context: dict = None) -> dict:
    if (a := html.find("<head>")) == -1:
        return None
    if (b := html.find('</head><body id="__django_nextjs_body"', a)) == -1:
        return None
    if (c := html.find('<div id="__django_nextjs_body_begin"', b)) == -1:
        return None
    if (d := html.find('<div id="__django_nextjs_body_end"', c)) == -1:
        return None

    context = context or {}
    context["django_nextjs__"] = {
        "section1": html[: a + len("<head>")],
        "section2": html[a + len("<head>") : b],
        "section3": html[b:c],
        "section4": html[c:d],
        "section5": html[d:],
    }

    return context


def _get_cookies(request):
    """
    Ensure we always send a CSRF cookie to Next.js server (if there is none in `request` object, generate one)
    Reason: We are going to issue GraphQL POST requests to fetch data in NextJS getServerSideProps.
            If this is the first request of user, there is no CSRF cookie and request fails,
            since GraphQL uses POST even for data fetching.
    Isn't this a vulnerability?
    No, as long as getServerSideProps functions are side effect free
    (i.e. dont use HTTP unsafe methods or GraphQL mutations).
    https://docs.djangoproject.com/en/3.2/ref/csrf/#is-posting-an-arbitrary-csrf-token-pair-cookie-and-post-data-a-vulnerability
    """
    return request.COOKIES | {settings.CSRF_COOKIE_NAME: get_csrf_token(request)}


def _get_headers(request):
    return {
        "x-real-ip": request.headers.get("X-Real-Ip", "") or request.META.get("REMOTE_ADDR", ""),
        "user-agent": request.headers.get("User-Agent", ""),
    }


def render_nextjs_page_to_string_sync(request: HttpRequest, template_name: str = "", context=None, using=None) -> str:
    page = requests.utils.quote(request.path_info.lstrip("/"))
    params = {k: request.GET.getlist(k) for k in request.GET.keys()}

    # Get HTML from Next.js server
    response = requests.get(
        f"{NEXTJS_SERVER_URL}/{page}",
        params=params,
        cookies=_get_cookies(request),
        headers=_get_headers(request),
    )
    html = response.text

    # Apply template_name if provided
    if template_name and (final_context := _get_context(html, context)) is not None:
        return render_to_string(template_name, context=final_context, request=request, using=using)

    # If no template_name, return original HTML
    return html


def render_nextjs_page_sync(
    request: HttpRequest, template_name: str = "", context=None, content_type=None, status=None, using=None
) -> str:
    content = render_nextjs_page_to_string_sync(request, template_name, context, using=using)
    return HttpResponse(content, content_type, status)


async def render_nextjs_page_to_string_async(
    request: HttpRequest, template_name: str = "", context=None, using=None
) -> str:
    page = requests.utils.quote(request.path_info.lstrip("/"))
    params = [(k, v) for k in request.GET.keys() for v in request.GET.getlist(k)]

    # Get HTML from Next.js server
    async with aiohttp.ClientSession(
        cookies=_get_cookies(request),
        headers=_get_headers(request),
    ) as session:
        async with session.get(f"{NEXTJS_SERVER_URL}/{page}", params=params) as response:
            html = await response.text()

    # Apply template_name if provided
    if template_name and (final_context := _get_context(html, context)) is not None:
        return await sync_to_async(render_to_string)(template_name, context=final_context, request=request, using=using)

    # If no template_name, return original HTML
    return html


async def render_nextjs_page_async(
    request: HttpRequest, template_name: str = "", context=None, content_type=None, status=None, using=None
) -> str:
    content = await render_nextjs_page_to_string_async(request, template_name, context, using=using)
    return HttpResponse(content, content_type, status)