Secure Contact Management API
=============================

This project is an asynchronous FastAPI service for private contact management.
It combines PostgreSQL persistence, Redis authentication caching, rotating JWT
tokens, role-based authorization, password recovery, and Cloudinary avatars.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   architecture
   security
   api

Quick verification
------------------

Run the complete automated quality gate with::

   pytest
   ruff check .
   sphinx-build -W -b html docs docs/_build/html

Indices
-------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
