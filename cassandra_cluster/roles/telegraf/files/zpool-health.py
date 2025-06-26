#!/usr/bin/env python3

import sys
import time


def main():
    """Wait for input to trigger next collection."""
    pools = sys.argv[1:]

    for pool in pools:
        state_path = f"/proc/spl/kstat/zfs/{pool}/state"
        nsec = int(time.time() * 1e9)
        try:
            with open(state_path) as file:
                state = file.read().strip()
            online = int(state == "ONLINE")
            metric = f'zfs_pool,pool={pool} online={online},state="{state}" {nsec}\n'
            sys.stdout.write(metric)
        except Exception:
            pass


if __name__ == "__main__":
    main()
