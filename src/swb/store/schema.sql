-- Results table per the spec: one row per question replicate. call_id doubles as the job id.
CREATE TABLE IF NOT EXISTS results (
    row_id               uuid PRIMARY KEY,
    call_id              uuid NOT NULL,
    run_id               text NOT NULL,
    condition_id         text NOT NULL,
    model                text NOT NULL,
    model_version        text,
    world                text NOT NULL,
    contrast             text,
    format               text NOT NULL,
    policy               text NOT NULL,
    vocab                text NOT NULL,
    length_tokens_target integer NOT NULL,
    input_tokens         integer NOT NULL,
    n_days               integer NOT NULL,
    seed                 bigint NOT NULL,
    reversal_m           integer,
    lag_days             integer,
    rung                 text,
    pair_side            text,
    diary_sha256         text NOT NULL,
    question_key         text NOT NULL,
    replicate            integer NOT NULL,
    option_order         jsonb NOT NULL,
    probabilities        jsonb NOT NULL,
    probabilities_source text NOT NULL,
    truth                text NOT NULL,
    truth_empirical      text,
    old_truth            text,
    true_rates           jsonb,
    baseline_scores      jsonb NOT NULL,
    latency_ms           integer NOT NULL,
    http_status          integer NOT NULL,
    cost_usd             numeric,
    is_mock              boolean NOT NULL,
    created_at           timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS results_call_id ON results (call_id);
CREATE INDEX IF NOT EXISTS results_run_model ON results (run_id, model);

-- Cumulative spend on capped models. Exactly one row.
CREATE TABLE IF NOT EXISTS budget (
    id     integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    tokens bigint NOT NULL DEFAULT 0,
    usd    numeric NOT NULL DEFAULT 0
);
INSERT INTO budget (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- One row per reserved job, so a resumed job replaces its reservation instead of adding one.
CREATE TABLE IF NOT EXISTS budget_reservations (
    job_id     text PRIMARY KEY,
    tokens     bigint NOT NULL,
    usd        numeric NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
