#!/usr/bin/env python3
"""Store Yoyo Chinese credentials securely in the macOS Keychain."""

from download_yoyo import YoyoError, configure_keychain_credentials


def main() -> int:
    try:
        configure_keychain_credentials()
    except (YoyoError, EOFError, KeyboardInterrupt) as exc:
        print(f"Erreur: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
