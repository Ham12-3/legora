"""Model access.

One interface (``LLMClient``), two implementations: OpenAI via the Responses
API with Structured Outputs, and a deterministic fake for tests and for
development without a key. Nothing outside this package constructs a client.
"""
