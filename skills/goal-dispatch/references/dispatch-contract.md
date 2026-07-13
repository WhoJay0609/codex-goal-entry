# Dispatch Contract

Every dispatched unit names its provider, expert instance, owned output, write
scope, dependencies, wait/continue rule, expected result, integration checkpoint,
conflict owner, and fallback. Provider choice is explicit and trace-visible.

Unknown provider availability blocks that unit; the backend never chooses or
silently substitutes a provider.
