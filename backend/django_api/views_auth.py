from django.views.decorators.http import require_GET, require_POST

from .helpers import create_session, error_response, exchange_code_for_openid, parse_request_data, require_user, success_response, upsert_user


@require_POST
def login_view(request):
    payload = parse_request_data(request)
    code = str(payload.get("code") or "").strip()
    if not code:
        return error_response("缺少登录 code", status=400)

    try:
        session = exchange_code_for_openid(code, request)
    except ValueError as exc:
        return error_response(str(exc), status=500)
    except PermissionError as exc:
        return error_response(str(exc), status=401)
    except Exception as exc:
        return error_response(f"微信登录失败：{exc}", status=500)

    user = upsert_user(session["openid"], session.get("unionid"))
    token, expires_at = create_session(user)
    return success_response(
        data={
            "token": token,
            "expires_at": expires_at,
            "user": {"id": user.id, "openid": user.openid},
        },
        message="登录成功",
    )


@require_GET
def me_view(request):
    user, error = require_user(request)
    if error:
        return error
    return success_response(data={"id": user.id, "openid": user.openid}, message="获取成功")


@require_POST
def logout_view(request):
    user, error = require_user(request)
    if error:
        return success_response(message="已退出")
    authorization = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION") or ""
    token = authorization.replace("Bearer ", "", 1).strip()
    if token:
        user.sessions.filter(token=token).delete()
    return success_response(message="已退出")