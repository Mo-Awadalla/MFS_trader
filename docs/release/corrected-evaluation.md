# Corrected numerical evaluations

Historical validation is preserved, not relabeled. `experiments.corrected_evaluations`
provides a reviewed, offline research-caller API that **executes the corrected
gauntlet**; it does not import a caller-supplied PASS. It never writes canonical
validation reports, frozen metadata/snapshots, or lifecycle statuses. No numerical,
strategy, risk, DSR trial-count-method, or promotion thresholds are changed.

## Evidence layout and failure semantics

For an existing Experiment, supply its full UUID and full experiment hash plus a
new canonical UUID identifying the evaluation:

```text
experiments/<original-uuid>/corrected_evaluations/v1/<evaluation-uuid>/request.json
experiments/<original-uuid>/corrected_evaluations/v1/<evaluation-uuid>/result.json
experiments/<original-uuid>/corrected_evaluations/v1/<evaluation-uuid>/disposition.json
experiments/<original-uuid>/corrected_evaluations/v1/requests/<request-sha256>.json
```

The ArtifactManager owns these paths. Complete JSON files are written to a temporary
file, flushed/fsynced, then published using atomic create-if-absent hard links.
Directory entries and reservation directories are fsynced as well. Durable corrected
publication requires a local POSIX filesystem supporting hard links and directory
fsync; Windows/network filesystem power-loss guarantees are not claimed.
There is no overwrite option. Concurrent attempts have one winner; duplicate IDs,
request identities (including a retry with a different UUID), and artifact collisions
are refused. A reserved attempt is permanent even if execution or publication is
interrupted. No partially written result becomes visible. Interrupted attempts
remain non-qualifying and cannot be retried in place. There is no overwrite/delete
or in-place resume switch. An unresolved attempt blocks qualification. Explicit
recovery appends an immutable `disposition.json` through
`abandon_corrected_evaluation(..., evaluation_id=..., operator=..., reason=...)`.
Only interrupted attempts without a completed result can be abandoned; this
cannot discard an unfavorable completed evaluation. The old ID, request claim,
request bytes and any late-arriving result remain preserved and unusable.
Abandonment itself never qualifies: a genuinely distinct evaluation begun after
the disposition must complete all gates. Existing older PASS results stay blocked.

`request.json` records:

- Original UUID/hash, canonical report identity and byte hash, original verdict and
  its hash (or explicit absence), and original lifecycle status at evaluation time.
- The complete frozen snapshot, including full selected parameters, data version,
  frequency, date window, costs, slippage, risk configuration, and random seed.
- Input identities, local paths and SHA-256 hashes; hashes/shapes/types of prepared
  data and stability sweep; the entire ordered declared trial parameter list;
  selected column; shared observation-index identity; complete return-matrix hash.
- Reviewed train/test function identities and source-file hashes, full caller
  configuration, explicit WFA configuration, MC configuration/frequency, fixed
  gate criteria, unchanged `M_eff_corr` DSR method and raw-trial sensitivity.
- Actual corrected source checkout commit, implementation-file hashes, tracked/
  untracked source cleanliness, report schema and MC/DSR formula versions. The
  commit is observed, not supplied by an operator. Dirty/untracked corrected source
  is unavailable, not attributed to HEAD. Callback source must be committed in the
  reviewed checkout and byte-identical to its committed version; qualification
  rechecks the callback file hashes.
- Installed-wheel-only execution cannot invent a missing source commit; evaluation
  requires a clean reviewed source checkout. CLI inspection can consume evidence
  only when implementation and caller-source bytes are still available and match.
  This is intentionally not a source-free installed-wheel evaluation workflow.

`result.json` binds the request SHA-256 and contains the actual gauntlet report,
completion timestamp, and separate corrected `PASS`, `FAIL`, or
`requiring_re_evaluation` verdict. Missing/invalid prerequisites, unavailable
MC/DSR evidence, execution errors, or changed inputs/source during computation are
explicitly unavailable, never a favorable fallback. Keyboard/process interruption
leaves a claimed incomplete attempt rather than falsely reporting completion.

## Reviewed caller API

Import `EvaluationInputs`, `evaluate_corrected`, and `run_current_evaluation` from
`experiments.corrected_evaluations`. Prepare data and strategy callbacks through
the reviewed research caller, using the frozen Experiment configuration. Then:

```python
inputs = EvaluationInputs(
    data=prepared_data,
    train_fn=train_fn,
    test_fn=test_fn,
    sweep_results=complete_sweep,
    param_columns=parameter_columns,
    search=complete_declared_search,
    input_files=input_identity_to_local_path,
    caller_config=full_caller_configuration,
    wfa_config=explicit_wfa_configuration,
    periods_per_year=observations_per_year,
    mc_num_paths=10000,
    mc_block_size=20,
    initial_capital=10000.0,
)
path = evaluate_corrected(
    registry, experiment.uuid, experiment.experiment_hash,
    evaluation_id=new_evaluation_uuid,
    inputs=inputs,
)
```

The objects above are caller-prepared evidence, not a JSON report or a verdict.
Build `complete_declared_search` with `validation.search.declared_search`, using
**every** trial's full parameter dictionary and return series in declared order,
an exact full frozen-parameter match, and a meaningful scope declaration. Sweeps
must have the same trial order. A winner-only matrix, dropped failed/flat trials,
missing full parameters, ambiguous selection, or undocumented search does not
qualify. Do not create synthetic trial provenance for historical candidates.
`caller_config` must disclose all preparation/strategy options and contain
`cost_model` and `slippage_model` equal to the frozen snapshot. No arbitrary
WFA gate overrides are exposed. OOS returns come from the executed WFA, not an
operator-supplied favorable OOS sample. The seed comes from the frozen snapshot.

For a **new** Experiment without a canonical report, the same reviewed execution
is available without pretending it is a historical correction:

```python
payload = run_current_evaluation(experiment, inputs)
# Existing canonical create-only publication, for a NEW Experiment only:
artifacts.write_json(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON, payload)
```

This function returns `{gauntlet, evaluation_provenance}` after running all checks;
it writes nothing. Existing ArtifactManager immutability prevents using the
example to replace an existing historical report. Ordinary research pipeline
reports may show a gauntlet PASS but lack complete current provenance: they remain
**unqualified for current paper readiness** until complete evidence exists.

The deterministic synthetic recipe in
`tests/unit/test_corrected_evaluations.py` exercises both APIs with a real gauntlet
and real temporary SQLite registry. It is not a historical strategy validation.

## Operator inspection and explicit unavailability

The standalone CLI has no broker, credential, network, or promotion operation:

```sh
python -m experiments.corrected_evaluation_cli \
  --experiment-root "$EXPERIMENT_ROOT" --uuid "$EXPERIMENT_UUID" \
  --hash "$EXPERIMENT_HASH" check

python -m experiments.corrected_evaluation_cli \
  --experiment-root "$EXPERIMENT_ROOT" --uuid "$EXPERIMENT_UUID" \
  --hash "$EXPERIMENT_HASH" unavailable \
  --evaluation-id "$NEW_EVALUATION_UUID" \
  --reason 'Complete searched-trial provenance is unavailable'
```

`check` exits 0 only for current numerical qualification, 1 for non-qualification,
and 2 for identity/usage/persistence errors. `unavailable` writes an immutable
non-qualifying result and exits 1; it never accepts a PASS flag. Actual evaluation
is through the Python caller API, not arbitrary Python-module loading from the CLI.
Use an isolated synthetic Experiment root for release verification. Do not run
write commands against historical production evidence as part of release tests.

After investigating an interrupted attempt, an operator may explicitly record:

```sh
python -m experiments.corrected_evaluation_cli \
  --experiment-root "$EXPERIMENT_ROOT" --uuid "$EXPERIMENT_UUID" \
  --hash "$EXPERIMENT_HASH" abandon --evaluation-id "$INTERRUPTED_EVALUATION_UUID" \
  --operator "$OPERATOR_ID" --reason 'Reviewed interrupted process; no completed result'
```

This exits 1 (still requiring re-evaluation), not 0. The API counterpart is
`abandon_corrected_evaluation(registry, uuid, hash, evaluation_id=..., operator=...,
reason=...)`. It neither removes evidence nor releases IDs/request identities.
The next distinct reviewed evaluation must start after the disposition.


## Qualification, manual approval, and boundaries

`check_current_qualification(registry, uuid, expected_hash)` returns `Qualification`
with `qualified`, `status`, `reason`, and optional `evaluation_id`.
`require_current_qualification(...)` raises `CorrectedQualificationError` when
not qualified. Neither changes lifecycle state. Paper admission must call this
before broker activity; the registry's transition into `PAPER_OPS` must enforce it
before mutation, including explicit resume and matrix-bypass requests. Live
promotion paths are outside this workflow and are not extended.

Qualification accepts either a complete current canonical envelope produced by
`run_current_evaluation`, or a complete corrected evaluation. It validates bound
identity, unchanged original bytes, source/formula/schema provenance, declared
search, and individual WFA/MC/DSR/stability values, including strict DSR/raw tail
probabilities. A report schema and `passed: true` alone are insufficient. A newer
unavailable/failed evaluation cannot be bypassed by selecting an older PASS;
incomplete/corrupt attempts fail closed. Changed numerical implementation bytes
invalidate earlier qualification without rewriting evidence.

Numerical qualification is **not** execution parity, broker-paper qualification,
operator approval, or live authorization. Manual UUID/hash confirmation and every
other applicable paper gate remain required. Diagnostic simulations may continue
to produce non-qualifying diagnostic evidence; that does not make them broker ready.

This API trusts reviewed research callers to faithfully compute trial returns and
apply declared costs. Source/input hashes make that claim auditable; they do not
prove the scientific truth of arbitrary callbacks or completeness of undocumented
human exploration. It is not a signature system protecting a filesystem from an
administrator who edits files outside ArtifactManager. Private input paths/hashes
may themselves be sensitive; do not publish correction artifacts or restricted data
without a separate review.

## Highlighted historical candidates

`119131fa-0f67-48d7-ab87-f20d81c70c1f` and
`a7dc94be-2578-4821-9706-cd268c013222` remain
**requiring_re_evaluation**: complete searched-trial provenance is unavailable.
No corrected PASS, report rewrite, frozen-snapshot change, or lifecycle transition
is claimed. The separately retained Yahoo window has 1,260 union bars, not the
historical replay's 5,405, so it does not establish original frozen input identity.
Independent attribution on that distinct window is not a historical rerun and does
not supply missing validation trial provenance.
