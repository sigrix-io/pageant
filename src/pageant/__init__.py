"""Pageant: a product's video lessons, recorded from the app itself, as code.

``import pageant`` loads the parts that need nothing but Python: a lesson's page and the pack of
them (``bundle``), its captions and chapters (``timeline``), its YouTube upload (``youtube``) and
the start hooks an app is filmed through (``apps``). Recording a lesson (``pageant.studio``) takes
the ``record`` extra, which none of these import.
"""

from pageant import apps, bundle, timeline, youtube

__version__ = "0.1.0"

__all__ = ["__version__", "apps", "bundle", "timeline", "youtube"]
