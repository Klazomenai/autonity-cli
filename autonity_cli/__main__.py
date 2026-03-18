"""
Autonity RPC Client
"""

import sys
from typing import Optional

from autonity.contracts.autonity import __version__ as protocol_version
from click import group, option, version_option

from . import config
from .commands import (
    account,
    block,
    contract,
    governance,
    node,
    protocol,
    token,
    tx,
    validator,
)
from .logging import enable_logging


@group(context_settings=dict(help_option_names=["-h", "--help"]))
@option("--verbose", "-v", is_flag=True, help="Enable additional output (to stderr)")
@option(
    "--auth-token",
    metavar="TOKEN",
    help=(
        "Bearer token for authenticated RPC endpoints "
        f"(falls back to '{config.AUTH_TOKEN_ENV_VAR}' env var "
        "or 'auth_token' in config file)."
    ),
)
@version_option(message=f"Autonity CLI v%(version)s (Protocol {protocol_version})")
def aut(verbose: bool, auth_token: Optional[str]) -> None:
    """
    Command line interface to interact with Autonity.
    """

    config.set_auth_token_from_cli(auth_token)

    if verbose:
        enable_logging()
    else:
        # Do not print the full callstack
        sys.tracebacklimit = 0


aut.add_command(node.node_group)
aut.add_command(block.block_group)
aut.add_command(tx.tx_group)
aut.add_command(protocol.protocol_group)
aut.add_command(governance.governance_group)
aut.add_command(validator.validator)
aut.add_command(account.account_group)
aut.add_command(token.token_group)
aut.add_command(contract.contract_group)
