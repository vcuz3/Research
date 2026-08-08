# Engine boundary

Fill and bracket accounting are imported from `forex/exploration_1/`. This
project owns only 5-minute resampling, the frozen displacement feature, dynamic
event/non-overlap selection, reversion exit timing, reporting, and controls.

The declared 17:00 New York boundary has no complete source bar. Boundary exits
therefore use the last attainable 5-minute open before the event (16:55), not an
invented 17:00 price.
