# JWT Authentication

`aut` supports JWT-authenticated RPC access via Sign-In with Ethereum (SIWE).
This allows operators to gate access to Autonity RPC endpoints, requiring
users to prove ownership of an Ethereum address that has been granted access
on-chain via a KeyRAAccessControl smart contract.

## How It Works

```
aut auth login
  1. Fetches a SIWE challenge message from the auth service
  2. Signs the message with your keyfile or Trezor
  3. Submits the signature to the auth service
  4. Receives a JWT token
  5. Stores the token in your config file

All subsequent aut commands automatically include the JWT as a
Bearer token in HTTP RPC requests.
```

The auth service (KeyRA) verifies your signature, checks that your address
has been granted access on-chain, and proxies a token request to a
jwt-auth-service instance. The returned JWT contains claims including
issuer, audience, user identity, and expiry.

## Prerequisites

- An Ethereum keyfile (created with `aut account new`) or a Trezor hardware wallet
- The address in the keyfile must have been granted access on the
  KeyRAAccessControl contract by an admin
- The URL of the auth service (KeyRA instance)
- The URL of the JWT-protected RPC endpoint

## Login

```bash
aut auth login \
  --keyfile ~/.autonity/keystore/mykey.json \
  --auth-service https://your-keyra-instance.example.com
```

You will be prompted for your keyfile password. To skip the interactive
prompt, set the `KEYFILEPWD` environment variable.

On success:

```
logged in as 0xYourAddress
token stored in /path/to/.autrc
```

The token is stored as `auth_token` in the first config file found by
walking from the current directory to parent directories (`.autrc`), or
`~/.config/aut/autrc` when the home directory is reached. If no config
file exists, a new `.autrc` is created in the current directory with
restrictive permissions (0600).

### Auth Service Resolution

The auth service URL is resolved in precedence order:

1. `--auth-service` CLI flag
2. `AUT_AUTH_SERVICE` environment variable
3. `auth_service` field in `.autrc` config file

**Important**: The auth service URL is the root domain of the KeyRA instance
(e.g., `https://your-keyra-instance.example.com`), NOT the RPC endpoint path.
The RPC endpoint (`/rpc`) is a separate service on the same gateway.

## Token Status

Inspect the current token without verifying its signature:

```bash
aut auth status
```

Output:

```json
{
  "expired": false,
  "expires_in": "7h 45m",
  "claims": {
    "iss": "https://your-keyra-instance.example.com",
    "aud": ["autonity-rpc-mainnet"],
    "sub": "user_0xYourAddress",
    "network": "default",
    "token_type": "parent",
    "exp": 1777000000
  }
}
```

The token is read from the same precedence chain as other config values:
`--auth-token` CLI flag > `AUT_AUTH_TOKEN` env var > `auth_token` in config file.

## Logout

Remove the token from the config file:

```bash
aut auth logout
```

This only removes `auth_token` from the config file. Tokens set via
`--auth-token` or `AUT_AUTH_TOKEN` env var are not affected.

## Using the Token for RPC Access

Once logged in, the JWT is automatically injected as an `Authorization: Bearer`
header on all HTTP RPC requests:

```bash
# Token is injected automatically
aut block get latest --rpc-endpoint https://your-rpc-endpoint.example.com/rpc

# Or set the endpoint in your .autrc (must have [aut] section — see .autrc.sample)
# echo "rpc_endpoint = https://your-rpc-endpoint.example.com/rpc" >> .autrc
aut block get latest
```

### Protocol-Specific Behaviour

| Protocol | Token Injection | Notes |
|----------|----------------|-------|
| HTTP/HTTPS | `Authorization: Bearer <token>` | Full support |
| WebSocket | Not supported | Warning printed with `--verbose` if token is configured |
| IPC | Not supported | Local communication, no auth needed |

## Configuration Reference

### Config File (`.autrc`)

```ini
[aut]
rpc_endpoint = https://your-rpc-endpoint.example.com/rpc
auth_service = https://your-keyra-instance.example.com
# auth_token is managed by `aut auth login` — do not edit manually
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `AUT_AUTH_SERVICE` | Auth service URL (KeyRA instance) |
| `AUT_AUTH_TOKEN` | JWT token (overrides config file) |
| `KEYFILEPWD` | Keyfile password (skips interactive prompt) |
| `WEB3_ENDPOINT` | RPC endpoint URL |

### Precedence

All configuration follows the same resolution order:

```
CLI flag > environment variable > config file
```

Empty or whitespace-only values at any level are treated as absent,
allowing fallthrough to the next source.

## Troubleshooting

### "no auth service configured"

Set the auth service URL via one of:

```bash
# CLI flag
aut auth login --auth-service https://your-keyra-instance.example.com

# Environment variable
export AUT_AUTH_SERVICE=https://your-keyra-instance.example.com

# Config file (.autrc must have [aut] section — see .autrc.sample)
# Add: auth_service = https://your-keyra-instance.example.com
```

### "cannot reach auth service at \<service\_url\>"

You may also see `auth service timed out at <service_url>`. In both
cases, the auth service URL is unreachable. Check:
- Network connectivity to the auth service
- The URL is the root domain, not the `/rpc` path
- HTTPS certificate is valid

### "authentication failed: 403"

Your address does not have access on the KeyRAAccessControl contract. An
admin must call `grantAccess(yourAddress)` before you can authenticate.

### "token response missing 'parent_token' or 'token' field"

The auth service returned a response without the expected token field. This
typically indicates a version mismatch between the CLI and the auth service.
Update to the latest version of `aut`.

### "challenge failed: 415" or "authentication failed: 415"

A 415 from the auth service (`/auth/challenge` or `/auth/token`) generally
indicates a version mismatch between the CLI and the auth service. The
`aut auth login` command sends JSON with `Content-Type: application/json`,
so if you see a 415 here, check that the auth service version matches the
CLI you are using.

### 415 from RPC endpoints after login

If you see a 415 from Autonity RPC endpoints *after* a successful login
(on JWT-authenticated requests), ensure you are running the latest version
of `aut`. Older versions may not include `Content-Type: application/json`
in Web3.py-based RPC requests due to a Web3.py 7.x compatibility issue
where custom `request_kwargs` headers replace the defaults rather than
merging with them.

## Further Reading

- [KeyRA](https://github.com/Klazomenai/KeyRA) — Auth gateway (SIWE verification, on-chain access control)
- [jwt-auth-service](https://github.com/Klazomenai/jwt-auth-service) — Token lifecycle management (mint, renew, revoke)
- [EIP-4361: Sign-In with Ethereum](https://eips.ethereum.org/EIPS/eip-4361) — SIWE specification
