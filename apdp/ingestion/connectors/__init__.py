"""Dealer data connectors.

A model-agnostic layer for pulling a dealer's account activity (MoMo,
bank-via-consent, internal feed, file drop) into the existing APDP
pipeline. Every connector emits the same raw envelope the Flink
normalizer already consumes, so nothing downstream cares which access
model a given dealer uses.

See docs/DEALER_CONNECTORS.md for the access-model decision record.
"""
