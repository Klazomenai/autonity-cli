"""Commands for managing authentication tokens."""

from typing import Any, Dict

import jwt
from click import ClickException, group

from .. import config
from ..config_file import remove_config_value
from ..utils import to_json


@group(name="auth")
def auth_group() -> None:
    """
    Commands related to authentication token management.
    """


@auth_group.command()
def login() -> None:
    """
    Authenticate via SIWE and store a token.
    """
    raise ClickException("not yet implemented — requires SIWE authentication flow (#5)")


@auth_group.command()
def status() -> None:
    """
    Show the current auth token status and decoded claims.

    Reads the token from --auth-token, AUT_AUTH_TOKEN env var,
    or auth_token in the config file (in that precedence order)
    and decodes its JWT claims without verifying the signature.
    """

    token = config.get_auth_token()
    if token is None:
        raise ClickException(
            "no auth token configured (use --auth-token, "
            f"'{config.AUTH_TOKEN_ENV_VAR}' env var, or 'auth_token' in config file)"
        )

    try:
        # Read alg from unverified header to support all JWT algorithms.
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
        claims: Dict[str, Any] = jwt.decode(
            token,
            algorithms=[alg],
            options={"verify_signature": False},
        )
    except jwt.exceptions.PyJWTError as exc:
        raise ClickException(f"failed to decode token: {exc}") from exc

    result: Dict[str, Any] = {}

    exp_raw = claims.get("exp")
    if exp_raw is not None:
        import time

        try:
            exp = float(exp_raw)
        except (TypeError, ValueError):
            exp = None

        if exp is not None:
            now = time.time()
            expired = now >= exp
            result["expired"] = expired

            diff = abs(exp - now)
            hours = int(diff // 3600)
            minutes = int((diff % 3600) // 60)

            if expired:
                result["expires_in"] = f"EXPIRED {hours}h {minutes}m ago"
            else:
                result["expires_in"] = f"{hours}h {minutes}m"

    result["claims"] = claims
    print(to_json(result, pretty=True))


@auth_group.command()
def logout() -> None:
    """
    Remove the auth token from the config file.

    Clears auth_token from the first config file found (.autrc in
    current/parent directories, or ~/.config/aut/autrc). Tokens set
    via --auth-token or AUT_AUTH_TOKEN env var are not affected.
    """

    path = remove_config_value("auth_token")
    if path is None:
        print("nothing to do (no auth_token in config file)")
    else:
        print(f"auth_token removed from {path}")
