"""Shared closed types for Bandwidth-Controllarr clients."""

from typing import Literal

BandwidthClientName = Literal["qbittorrent", "sabnzbd"]

DOWNLOAD_HISTORY_LIMIT = 10

# Upper bound on queue rows returned per downloader. The dashboard pages through
# these five at a time; the cumulative total is reported separately so a queue
# deeper than this cap is still counted honestly.
QUEUE_ITEM_LIMIT = 100
