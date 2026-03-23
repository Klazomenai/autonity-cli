"""Commands for managing authentication tokens."""

from typing import Any, Dict, Optional

import click
import jwt
import requests
from click import ClickException, group

from .. import config
from ..auth import authenticator
from ..config_file import remove_config_value, set_config_value
from ..options import authentication_options
from ..utils import to_json


@group(name="auth")
def auth_group() -> None:
    """
    Commands related to authentication token management.
    """


@auth_group.command()
@authentication_options()
@click.option("--auth-service", metavar="URL", default=None, help="KeyRA auth service URL")
def login(keyfile: Optional[str], trezor: Optional[str], auth_service: Optional[str]) -> None:
    """
    Authenticate via SIWE and store a token.

    Signs a challenge message from the auth service using
    --keyfile or --trezor, submits the signature, and stores
    the returned JWT in the config file.
    """

    service_url = config.get_auth_service(auth_service)
    # Strip trailing slash for consistent URL joining
    service_url = service_url.rstrip("/")

    with authenticator(keyfile=keyfile, trezor=trezor) as auth:
        address = str(auth.address)

        # 1. Fetch challenge from auth service
        try:
            resp = requests.post(
                f"{service_url}/auth/challenge",
                json={"address": address},
                timeout=30,
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise ClickException(
                f"cannot reach auth service at {service_url}"
            ) from exc
        except requests.Timeout as exc:
            raise ClickException(
                f"auth service timed out at {service_url}"
            ) from exc
        except requests.HTTPError as exc:
            raise ClickException(
                f"challenge failed: {resp.status_code} {resp.text}"
            ) from exc

        challenge = resp.json()
        message = challenge.get("message")
        if not message:
            raise ClickException("challenge response missing 'message' field")

        # 2. Sign the SIWE message
        signature = auth.sign_message(message)
        sig_hex = "0x" + signature.hex()

        # 3. Submit signature, receive token
        try:
            resp = requests.post(
                f"{service_url}/auth/token",
                json={"message": message, "signature": sig_hex},
                timeout=30,
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise ClickException(
                f"cannot reach auth service at {service_url}"
            ) from exc
        except requests.Timeout as exc:
            raise ClickException(
                f"auth service timed out at {service_url}"
            ) from exc
        except requests.HTTPError as exc:
            raise ClickException(
                f"authentication failed: {resp.status_code} {resp.text}"
            ) from exc

        token_data = resp.json()
        token = token_data.get("token")
        if not token:
            raise ClickException("token response missing 'token' field")

        # 4. Store token in config file
        path = set_config_value("auth_token", token)
        print(f"logged in as {address}")
        print(f"token stored in {path}")


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
