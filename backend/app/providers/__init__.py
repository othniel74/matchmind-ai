"""Adapters from data providers' event formats to Pitchlight's event contract (core.Event).

An adapter turns a provider's events into Pitchlight events and reports what it could not
represent. Every adapted event then passes the same StreamValidator as the synthetic feed, so
claims, statistics, pass networks and narratives run unchanged on provider data.
"""
