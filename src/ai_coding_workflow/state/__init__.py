"""State management: operation logs, retry tracking, frontmatter parsing.

Stateless from the server's perspective — all state lives in the workspace
filesystem (operation logs, design doc frontmatter) and external systems
(Jira ticket status, GitHub PR state). This module just reads and writes
those state representations consistently.
"""
