"""`python -m codebase_agent_setup` behaves exactly like the installed cbsetup command."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
