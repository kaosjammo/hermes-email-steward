These are synthetic database states produced by the actual predecessor product
`3efca2b3f3831f1d45cd06c4647a4bf5555893f7` through `legacy_owner_process.py`
(`seed`, each named action, `once`). Only product code and its OAuth manifest
were read from the protected historical repository. No historical source,
credentials, live mail, private instruction files or repository history is
included here. Addresses, messages, grants and provider responses are synthetic.

`{{CASE_HOME}}` replaces the synthetic database's absolute home. The source
location in the expected seed record is a provenance label. Public CI restores
these SQLite dumps and runs the actual successor in a separate process. Setting
`ES_LEGACY_SOURCE` additionally regenerates each database with that predecessor
before reopening it; this stronger two-version process qualification was run
locally. The fixture route is a persisted-state regression, not evidence that
CI obtained or executed private predecessor code.
