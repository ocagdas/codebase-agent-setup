"""codebase-agent-setup tooling distribution."""

from .resources import RESOURCE_ROOT, PACKAGE_ROOT

# Consumer tools remain authored under project/. Wheels contain the same payload
# beside this package; source/editable execution resolves it from the checkout.
if RESOURCE_ROOT != PACKAGE_ROOT:
    __path__.append(str(RESOURCE_ROOT))
