# Security

Please report a vulnerability in this SDK privately to **contact@satelit.md**, not in a public issue. Say what you found, how to reproduce it, and which version you used. We answer every report.

If you leaked an API key (in a commit, a log, a page), revoke it in the [console](https://developer.satelit.md/en/console/) at once and create a new one: the console is the only place a key can be revoked.

The SDK never logs or prints the key; `repr()` of a client shows only whether a key is set.
