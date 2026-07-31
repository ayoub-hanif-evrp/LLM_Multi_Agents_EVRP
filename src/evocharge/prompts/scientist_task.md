# Scientist Agent — Task

Given a validated Analyst report, propose exactly three distinct algorithmic hypotheses.

## Analyst validation hash
{{analyst_validation_hash}}

## Analyst report
```json
{{analyst_report}}
```

## Dataset contract summary
```json
{{dataset_contract_summary}}
```

## Objective summary
```json
{{objective_summary}}
```

## Approved primitive catalogue (conceptual; not executable)
```json
{{approved_primitive_catalogue}}
```

## Hypothesis constraints
```json
{{hypothesis_constraints}}
```

## Prior hypothesis summaries (may be empty)
```json
{{prior_hypothesis_summaries}}
```

Return a ScientistReport JSON object with exactly three hypotheses. Each `required_primitives` entry must be a catalogue `primitive_id`.
